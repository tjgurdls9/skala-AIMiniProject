"""Command, test and install policy plus the Docker argument builder; policy and recording only, never results."""
from dataclasses import dataclass
import re
import subprocess

from backend.contracts import SECRET, DomainError, digest, require
from backend.store import uid
from runner.registry_hosts import REGISTRY_HOSTS
from runner.sandbox import Sandbox
from runner.workspace import relative_parts

EXECUTABLES = ("node", "npm", "python", "python3")
TOOL_POLICY = dict(
    executables=list(EXECUTABLES), timeout_default=60, timeout_max=300, output_bytes=65536, max_args=32, arg_bytes=500,
    network="none", install_managers=["npm", "pip"], max_packages=20,
    registry_hosts=list(REGISTRY_HOSTS),
    limits=dict(pids=64, memory="512m", cpus="1", user="65534:65534"))
DENIED_NPM = frozenset({"install", "i", "add", "ci", "update", "exec", "x", "publish", "link", "init", "create"})
DENIED_MODULES = frozenset({"pip", "ensurepip"})
IMAGE = re.compile(r"(?:[a-z0-9][a-z0-9._/-]*@)?sha256:[a-f0-9]{64}")
PIP_SPEC = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}(?:==[A-Za-z0-9][A-Za-z0-9._+!-]{0,39})?")
NPM_SPEC = re.compile(r"(?:@[a-z0-9][a-z0-9._-]{0,99}/)?[a-z0-9][a-z0-9._-]{0,99}(?:@[A-Za-z0-9][A-Za-z0-9._^~<>=|-]{0,39})?")
SPECS = dict(pip=PIP_SPEC, npm=NPM_SPEC)
CONTAINER_WORK, CONTAINER_DEPS = "/work", "/deps"


def tool_policy_digest():
    return digest(TOOL_POLICY)


@dataclass(frozen=True)
class CommandResult:
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    truncated: bool


def redact(text):
    return SECRET.sub("[redacted]", text)


def validate_command(argv, cwd=".", timeout=TOOL_POLICY["timeout_default"]):
    require(isinstance(argv, list) and argv and all(isinstance(a, str) and "\x00" not in a for a in argv),
            "FORBIDDEN", "셸 문자열이 아닌 인자 배열이 필요합니다.", 403)
    require(len(argv) <= TOOL_POLICY["max_args"] and all(len(a.encode()) <= TOOL_POLICY["arg_bytes"] for a in argv),
            "INVALID_COMMAND", "인자 개수나 길이 한도를 넘었습니다.", 422)
    require(argv[0] in EXECUTABLES, "FORBIDDEN", "허용된 실행 파일이 아닙니다.", 403)
    if argv[0] == "npm":
        first = next((a for a in argv[1:] if not a.startswith("-")), None)
        require(first not in DENIED_NPM, "FORBIDDEN", "의존성 설치는 install_dependencies 도구로만 합니다.", 403)
    for flag, module in zip(argv, argv[1:]):
        require(not (flag == "-m" and module in DENIED_MODULES), "FORBIDDEN", "의존성 설치는 install_dependencies 도구로만 합니다.", 403)
    relative_parts(cwd, allow_dot=True)
    require(type(timeout) is int and 0 < timeout <= TOOL_POLICY["timeout_max"], "INVALID_COMMAND", "제한 시간이 범위를 벗어났습니다.", 422)
    return dict(argv=list(argv), cwd=cwd, timeout=timeout)


def validate_test_command(argv):
    is_python = len(argv) > 2 and argv[0] in ("python", "python3") and argv[1] == "-m" and argv[2] in ("pytest", "unittest")
    is_node = len(argv) > 1 and argv[0] == "node" and argv[1] == "--test"
    is_npm = len(argv) > 1 and argv[0] == "npm" and (argv[1] == "test" or argv[1:3] == ["run", "test"])
    require(is_python or is_node or is_npm, "FORBIDDEN",
            "시험 실행기 형식이 아닙니다. 허용: python -m unittest ..., python -m pytest ..., node --test ..., npm test", 403)


def package_name(manager, spec):
    if manager == "pip":
        return spec.split("==")[0].lower().replace("_", "-")
    return spec[: spec.index("@", 1)] if "@" in spec[1:] else spec


def validate_install(manager, packages):
    require(manager in TOOL_POLICY["install_managers"], "FORBIDDEN", "허용된 패키지 관리자가 아닙니다.", 403)
    require(isinstance(packages, list) and 0 < len(packages) <= TOOL_POLICY["max_packages"] and
            all(isinstance(p, str) and SPECS[manager].fullmatch(p) for p in packages),
            "INVALID_COMMAND", "레지스트리 패키지 이름과 버전만 허용됩니다.", 422)
    return list(packages)


class DockerExecutor:
    """Runs one argv in a fresh locked-down container; `runner` is injectable so tests never start Docker."""

    LANGUAGES = dict(python="python", python3="python", node="node", npm="node")

    def __init__(self, images, runner=subprocess.run):
        """`images` is one digest-pinned reference for every program, or {"python": ref, "node": ref} per language."""
        mapping = dict(python=images, node=images) if isinstance(images, str) else dict(images or {})
        require(bool(mapping) and set(mapping) <= {"python", "node"} and all(isinstance(v, str) and IMAGE.fullmatch(v) for v in mapping.values()),
                "RUNTIME_UNAVAILABLE", "digest로 고정한 실행 이미지가 필요합니다.")
        self.images, self.runner = mapping, runner

    def image_for(self, program):
        image = self.images.get(self.LANGUAGES.get(program))
        require(image is not None, "RUNTIME_UNAVAILABLE", "이 프로그램을 실행할 고정 이미지가 없습니다.")
        return image

    def build_args(self, name, workspace, argv, cwd, network, env, deps, deps_writable):
        container_env = {"HOME": "/tmp", "PYTHONDONTWRITEBYTECODE": "1", **(env or {})}
        args = ["run", "--rm", *Sandbox.limits(name, network), "--mount", f"type=bind,src={workspace},dst={CONTAINER_WORK}",
                "--workdir", CONTAINER_WORK if cwd == "." else f"{CONTAINER_WORK}/{cwd}"]
        if deps is not None:
            args += ["--mount", f"type=bind,src={deps},dst={CONTAINER_DEPS}" + ("" if deps_writable else ",readonly")]
            container_env.update(PYTHONPATH=f"{CONTAINER_DEPS}/py", NODE_PATH=f"{CONTAINER_DEPS}/node_modules",
                                 PATH=f"{CONTAINER_DEPS}/node_modules/.bin:/usr/local/bin:/usr/bin:/bin")
        for key, value in sorted(container_env.items()):
            args += ["--env", f"{key}={value}"]
        return ["docker", *args, self.image_for(argv[0]), *argv]

    def run(self, workspace, argv, cwd, timeout, network="none", env=None, deps=None, deps_writable=False):
        name = "lifecycle-" + uid()
        args = self.build_args(name, workspace, argv, cwd, network, env, deps, deps_writable)
        try:
            process = self.runner(args, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout, shell=False)
        except subprocess.TimeoutExpired:
            self.runner(["docker", "rm", "-f", name], stdin=subprocess.DEVNULL, capture_output=True, timeout=30, shell=False)
            return CommandResult(None, "", "", True, False)
        except OSError as error:
            raise DomainError("RUNTIME_UNAVAILABLE", "격리 실행기를 사용할 수 없습니다.", 503) from error
        cap = TOOL_POLICY["output_bytes"]
        out, err = process.stdout or b"", process.stderr or b""
        return CommandResult(process.returncode, redact(out[:cap].decode(errors="replace")), redact(err[:cap].decode(errors="replace")),
                             False, len(out) > cap or len(err) > cap)
