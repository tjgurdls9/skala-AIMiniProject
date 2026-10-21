"""Per-task commits, kept history and a generic candidate freeze from the app's own declaration.

The repository lives OUTSIDE the workspace the sandbox can write, so a program running in a container can never plant
hooks, config or filters that the host's git would execute. The Dockerfile is generated from a validated declaration;
it installs and runs nothing while building."""
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile

from backend.contracts import DomainError, digest, require
from runner.commands import IMAGE, DockerExecutor, validate_command
from runner.tdd_gate import is_test_path
from runner.workspace import Workspace

APP_FILE = "lifecycle.app.json"
SERVICE_PORT = 8080
GIT_SAFE = ["-c", "core.hooksPath=" + os.devnull, "-c", "core.fsmonitor=false", "-c", "core.attributesFile=" + os.devnull,
            "-c", "commit.gpgsign=false", "-c", "user.name=Lifecycle", "-c", "user.email=lifecycle@localhost"]


def git_dir_of(workspace):
    return Path(str(workspace) + ".git")


def _git(workspace, *args, check=True):
    env = {"PATH": os.environ.get("PATH", os.defpath), "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_ATTR_NOSYSTEM": "1",
           "GIT_TERMINAL_PROMPT": "0"}
    done = subprocess.run(["git", *GIT_SAFE, "--git-dir", str(git_dir_of(workspace)), "--work-tree", str(workspace), *args],
                          capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL, timeout=120)
    if check and done.returncode:
        raise DomainError("TEMPORARILY_UNAVAILABLE", "작업 공간 저장소 작업에 실패했습니다: " + done.stderr.strip()[:200], 503)
    return done.stdout.strip()


def _has_head(workspace):
    return subprocess.run(["git", "--git-dir", str(git_dir_of(workspace)), "rev-parse", "--verify", "-q", "HEAD"],
                          capture_output=True, stdin=subprocess.DEVNULL, env={"PATH": os.environ.get("PATH", os.defpath)}).returncode == 0


def commit_task(workspace, task_id, title):
    """Commit the workspace as one task step and return the commit; no changes means no new commit."""
    workspace = Path(workspace)
    Workspace(workspace).sanitize()   # links and special files never enter the history
    if not git_dir_of(workspace).exists():
        _git(workspace, "init", "-q", "-b", "main")
    _git(workspace, "add", "-A")
    changed = subprocess.run(["git", *GIT_SAFE, "--git-dir", str(git_dir_of(workspace)), "--work-tree", str(workspace), "diff", "--cached", "--quiet"],
                             capture_output=True, stdin=subprocess.DEVNULL, env={"PATH": os.environ.get("PATH", os.defpath)}).returncode != 0
    if changed or not _has_head(workspace):
        _git(workspace, "commit", "-q", "--allow-empty", "-m", f"task: {title} [{task_id}]")
    return _git(workspace, "rev-parse", "HEAD")


def installed_modules(deps):
    """Import names each installed Python distribution provides ({normalised distribution: [top-level modules]}), read from its metadata."""
    result = {}
    for info in sorted(Path(deps).glob("py/*.dist-info")):
        meta = info / "METADATA"
        found = re.search(r"^Name:\s*(\S+)", meta.read_text(errors="replace"), re.M) if meta.is_file() else None
        if not found:
            continue
        top = info / "top_level.txt"
        if top.is_file():
            modules = top.read_text().split()
        else:
            record = info / "RECORD"
            modules = []
            for line in (record.read_text(errors="replace").splitlines() if record.is_file() else []):
                first = line.split(",")[0].split("/")[0]
                if first and not first.startswith(".") and ".dist-info" not in first and first != "__pycache__":
                    modules.append(first[:-3] if first.endswith(".py") else first)
        result[re.sub(r"[-_.]+", "-", found.group(1)).lower()] = sorted(set(modules))
    return result


def _leave_out_tests(root):
    def ignore(directory, names):
        relative = Path(directory).relative_to(root)
        return [n for n in names if n == ".git" or n in ("tests", "__tests__") or
                ((Path(directory) / n).is_file() and is_test_path((relative / n).as_posix()))]
    return ignore


def validate_app_manifest(value):
    require(isinstance(value, dict) and set(value) == {"runtime", "start", "port", "health"}, "INVALID_STATE",
            f"{APP_FILE}에는 runtime, start, port, health만 있어야 합니다.", 409)
    require(value["runtime"] in ("python", "node"), "INVALID_STATE", "runtime은 python 또는 node여야 합니다.", 409)
    require(value["port"] == SERVICE_PORT and type(value["port"]) is int, "INVALID_STATE", f"앱은 {SERVICE_PORT} 포트에서 들어야 합니다.", 409)
    require(isinstance(value["health"], str) and value["health"].startswith("/") and len(value["health"]) <= 200 and " " not in value["health"],
            "INVALID_STATE", "health는 /로 시작하는 경로여야 합니다.", 409)
    start = value["start"]
    require(isinstance(start, list) and 1 <= len(start) <= 16, "INVALID_STATE", "start는 인자 배열이어야 합니다.", 409)
    validate_command(start)
    require(DockerExecutor.LANGUAGES.get(start[0]) == value["runtime"], "INVALID_STATE", "start 프로그램이 runtime과 맞지 않습니다.", 409)
    return value


def render_dockerfile(base_image, manifest):
    require(isinstance(base_image, str) and IMAGE.fullmatch(base_image), "RUNTIME_UNAVAILABLE", "digest로 고정한 기반 이미지가 필요합니다.")
    validate_app_manifest(manifest)
    return "\n".join([
        f"FROM {base_image}", "WORKDIR /app", "COPY app/ /app/", "COPY deps/ /deps/",
        "ENV PYTHONPATH=/deps/py NODE_PATH=/deps/node_modules PATH=/deps/node_modules/.bin:/usr/local/bin:/usr/bin:/bin HOME=/tmp PYTHONDONTWRITEBYTECODE=1",
        f"EXPOSE {SERVICE_PORT}", "USER 65534:65534", "CMD " + json.dumps(manifest["start"]), ""])


def freeze_model(engine, workspace, deps, base_image):
    """Turn the committed workspace into a candidate: a clone at the commit plus an image built offline from a generated Dockerfile."""
    workspace, deps = Path(workspace), Path(deps)
    require(not any(p.is_symlink() for p in workspace.rglob("*")), "FORBIDDEN", "작업 공간에 심볼릭 링크가 있어 후보로 고정할 수 없습니다.", 403)
    require(git_dir_of(workspace).exists() and not _git(workspace, "status", "--porcelain"), "INVALID_STATE",
            "작업이 커밋되지 않은 변경이 있습니다. 모든 변경은 작업 커밋에 포함돼야 후보가 됩니다.", 409)
    declaration = workspace / APP_FILE
    require(declaration.is_file(), "INVALID_STATE", f"앱 시작 선언 파일 {APP_FILE}이 없습니다. 앱을 어떻게 시작하는지 선언해야 후보가 됩니다.", 409)
    try:
        app = validate_app_manifest(json.loads(declaration.read_text()))
    except ValueError:
        raise DomainError("INVALID_STATE", f"{APP_FILE}을 JSON으로 해석할 수 없습니다.", 409) from None
    base = base_image if isinstance(base_image, str) else base_image.get(app["runtime"])
    commit = _git(workspace, "rev-parse", "HEAD")
    manifest = Workspace(workspace).manifest()
    candidate_id = digest(dict(commit=commit, manifest=manifest)).split(":")[1]
    candidate = engine.root / "candidates" / candidate_id
    if not candidate.exists():
        candidate.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", *GIT_SAFE, "clone", "-q", "--no-hardlinks", str(git_dir_of(workspace)), str(candidate)], check=True,
                       capture_output=True, stdin=subprocess.DEVNULL, env={"PATH": os.environ.get("PATH", os.defpath), "GIT_CONFIG_GLOBAL": os.devnull})
    with tempfile.TemporaryDirectory(dir=engine.root) as temp:
        context = Path(temp)
        # The image carries the app, not the builder's tests: a check can then only exercise the implementation itself.
        shutil.copytree(candidate, context / "app", ignore=_leave_out_tests(candidate), symlinks=True)
        shutil.copytree(deps, context / "deps", symlinks=True) if deps.exists() else (context / "deps").mkdir()
        (context / "Dockerfile").write_text(render_dockerfile(base, app))
        iid = context / "image-id"
        engine.docker("build", "--network=none", "--iidfile", iid, "-f", context / "Dockerfile", context, timeout=300)
        image = iid.read_text().strip()
    return dict(candidate_id=candidate_id, commit_sha=commit, image_digest=image, manifest=manifest, path=str(candidate), app=app,
                excluded_tests=sorted(p for p in manifest if is_test_path(p)), dependency_modules=installed_modules(deps) if deps.exists() else {})
