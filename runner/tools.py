"""Model-callable workspace, command and install tools; every call, allowed or denied, lands in the immutable ledger."""
import json
from pathlib import Path

from backend.contracts import DomainError, digest, require
from backend.store import now
from runner.commands import (TOOL_POLICY, package_name, redact, validate_command, validate_install, validate_test_command)
from runner.tdd_gate import TDD_KINDS, is_test_path, mutated_paths, progress
from runner.workspace import Workspace

READ_ROLES = frozenset({"builder", "validator", "security"})
BUILD_ROLES = frozenset({"builder"})
EXCERPT_BYTES = 2048
LOCK_FILES = dict(pip="requirements.lock", npm="package-lock.json")


class EscalateToUser(DomainError):
    """The request is outside the approved plan; the caller must stop and hand it to the user (needs_input)."""
    needs_input = True

    def __init__(self, message):
        super().__init__("FORBIDDEN", message, 403)


def excerpt(text):
    return redact(text.encode()[:EXCERPT_BYTES].decode(errors="ignore"))


class ToolBox:
    def __init__(self, authority, store, workspace, executor, *, allowed_dependencies=None, registry_network=None,
                 registry_env=None, deps_dir=None):
        self.authority, self.store, self.workspace, self.executor = authority, store, workspace, executor
        self.allowed_dependencies, self.registry_network = allowed_dependencies, registry_network
        self.registry_env, self.deps_dir = registry_env, deps_dir

    @classmethod
    def from_scope(cls, store, scope, executor, registry_network=None, registry_env=None):
        """Bind a toolbox to one server-issued capability; scope, dependency range and workspace come from the job, not the model."""
        def who():
            row, _ = scope.authority()
            options = json.loads(row["context"] or "{}").get("options", {})
            return dict(role=row["role"], run_id=row["run_id"], job_id=row["job_id"], attempt_id=row.get("attempt_id"),
                        task_id=options.get("task_id"), task_kind=options.get("task_kind"))
        row, _ = scope.authority()
        require(row["workspace"] is not None, "FORBIDDEN", "작업 공간이 없습니다.", 403)
        options = json.loads(row["context"] or "{}").get("options", {})
        workspace = Path(row["workspace"])
        allowed = {m: set(names) for m, names in options.get("allowed_dependencies", {}).items()} or None
        deps = Path(str(workspace) + ".deps")
        deps.mkdir(exist_ok=True)
        return cls(who, store, Workspace(workspace, tuple(options.get("write_scope", ("**",)))), executor, allowed_dependencies=allowed,
                   registry_network=registry_network, registry_env=registry_env, deps_dir=deps)

    # -- ledgered call wrapper ----------------------------------------
    def _call(self, tool, args, roles, action):
        who = self.authority()  # a revoked capability stops here and leaves no entry
        started = now()
        try:
            require(who["role"] in roles, "FORBIDDEN", "이 역할에 허용되지 않은 도구입니다.", 403)
            result, extra = action(who)
        except DomainError as error:
            self._record(who, tool, args, started, ok=False, error_code=error.code)
            raise
        self._record(who, tool, args, started, ok=True, **extra)
        return result

    def _record(self, who, tool, args, started, **fields):
        self.store.record_tool_call(dict(
            run_id=who["run_id"], job_id=who.get("job_id"), attempt_id=who.get("attempt_id"), task_id=who.get("task_id"),
            role=who["role"], tool=tool, args=args, started_at=started, finished_at=now(), **fields))

    # -- files ----------------------------------------------------------
    def list_files(self):
        return self._call("list_files", {}, READ_ROLES, lambda who: self._ok(dict(files=self.workspace.list_files())))

    def read_file(self, path):
        return self._call("read_file", dict(path=path), READ_ROLES, lambda who: self._ok(self.workspace.read(path)))

    def write_file(self, path, content, expected_digest=None):
        args = dict(path=path, expected_digest=expected_digest, content_digest=digest(content) if isinstance(content, str) else None,
                    content_bytes=len(content.encode()) if isinstance(content, str) else None)
        return self._call("write_file", args, BUILD_ROLES, lambda who: self._mutate(who, [path], lambda: self.workspace.write(path, content, expected_digest)))

    def delete_file(self, path, expected_digest):
        return self._call("delete_file", dict(path=path, expected_digest=expected_digest), BUILD_ROLES,
                          lambda who: self._mutate(who, [path], lambda: self.workspace.delete(path, expected_digest)))

    def move_file(self, source, target, expected_digest):
        return self._call("move_file", dict(source=source, target=target, expected_digest=expected_digest), BUILD_ROLES,
                          lambda who: self._mutate(who, [source, target], lambda: self.workspace.move(source, target, expected_digest)))

    def _mutate(self, who, paths, action):
        """Run a file mutation after the server-side RED gate: implementation files stay locked until failing tests are on record."""
        if who.get("task_kind") in TDD_KINDS and any(not is_test_path(p) for p in paths):
            state = progress(self.store.tool_calls(who["run_id"], who.get("task_id")), who["task_kind"])
            require(state.phase != "red", "FORBIDDEN", state.message, 403)
        return self._ok(action())

    @staticmethod
    def _ok(result):
        return result, dict(result_digest=digest(result))

    # -- commands -------------------------------------------------------
    def run_command(self, argv, cwd=".", timeout=TOOL_POLICY["timeout_default"]):
        return self._call("run_command", dict(argv=argv, cwd=cwd, timeout=timeout), BUILD_ROLES,
                          lambda who: self._execute(validate_command(argv, cwd, timeout)))

    def run_tests(self, argv, cwd=".", timeout=TOOL_POLICY["timeout_default"]):
        def action(who):
            command = validate_command(argv, cwd, timeout)
            validate_test_command(command["argv"])
            return self._execute(command)
        return self._call("run_tests", dict(argv=argv, cwd=cwd, timeout=timeout), BUILD_ROLES, action)

    def _execute(self, command, network="none", env=None, deps_writable=False):
        result = self.executor.run(self.workspace.root, command["argv"], command["cwd"], command["timeout"], network=network, env=env,
                                   deps=self.deps_dir, deps_writable=deps_writable)
        public = dict(exit_code=result.exit_code, stdout=redact(result.stdout), stderr=redact(result.stderr),
                      timed_out=result.timed_out, truncated=result.truncated, removed_links=self.workspace.sanitize())
        return public, dict(exit_code=result.exit_code, stdout_digest=digest(result.stdout), stderr_digest=digest(result.stderr),
                            stdout_excerpt=excerpt(result.stdout), stderr_excerpt=excerpt(result.stderr), result_digest=digest(public))

    # -- dependencies ---------------------------------------------------
    def install_dependencies(self, manager, packages):
        return self._call("install_dependencies", dict(manager=manager, packages=packages), BUILD_ROLES,
                          lambda who: self._install(manager, packages))

    def _install(self, manager, packages):
        packages = validate_install(manager, packages)
        allowed = (self.allowed_dependencies or {}).get(manager)
        if allowed is None or any(package_name(manager, p) not in allowed for p in packages):
            raise EscalateToUser("승인된 계획의 의존성 범위 밖입니다. 사용자의 계획 수정/승인이 필요합니다.")
        require(self.registry_network is not None and self.deps_dir is not None, "RUNTIME_UNAVAILABLE",
                "허용 목록 레지스트리 프록시가 구성되지 않았습니다.", 503)
        install = dict(pip=["python", "-m", "pip", "install", "--no-input", "--disable-pip-version-check", "--only-binary=:all:",
                            "--target", "/deps/py", *packages],
                       npm=["npm", "install", "--ignore-scripts", "--no-audit", "--no-fund", "--prefix", "/deps", *packages])[manager]
        public, extra = self._execute(dict(argv=install, cwd=".", timeout=TOOL_POLICY["timeout_max"]), self.registry_network,
                                      self.registry_env, deps_writable=True)
        if public["exit_code"] != 0:
            return public, extra
        freeze = dict(pip=["python", "-m", "pip", "freeze", "--path", "/deps/py"],
                      npm=["node", "-e", "process.stdout.write(require('fs').readFileSync('/deps/package-lock.json','utf8'))"])[manager]
        locked, _ = self._execute(dict(argv=freeze, cwd=".", timeout=60))
        lock_file, public = LOCK_FILES[manager], dict(public, lock_file=None, lock_digest=digest(locked["stdout"]))
        if locked["exit_code"] == 0 and not locked["truncated"]:
            try:
                self.workspace.write(lock_file, locked["stdout"], self._current_digest(lock_file), enforce_scope=False)
                public["lock_file"] = lock_file
            except DomainError:
                pass  # an oversized or conflicting lock is reported by lock_digest; the install result itself stands
        return public, dict(extra, result_digest=digest(public))

    def _current_digest(self, name):
        path = self.workspace.root / name
        return self.workspace.read(name)["content_digest"] if path.exists() else None
