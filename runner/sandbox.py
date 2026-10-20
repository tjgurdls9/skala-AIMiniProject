"""Fixed Docker operations. Model output never becomes a shell command or mount."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from backend.contracts import ROOT, SECRET, digest, require
from backend.store import uid
from runner.access import WRITABLE_FILES
from runner.model import ModelUnavailable

PATCH_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["summary", "files"], "properties": {
    "summary": {"type": "string", "maxLength": 2000},
    "files": {"type": "array", "maxItems": 4, "items": {"type": "object", "additionalProperties": False,
        "required": ["path", "content"], "properties": {"path": {"enum": list(WRITABLE_FILES)},
        "content": {"type": "string", "maxLength": 65536}}}}}}


class Sandbox:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def docker(*args, timeout=120):
        env = {k: os.environ[k] for k in ("PATH", "HOME", "DOCKER_HOST", "DOCKER_CONTEXT") if k in os.environ}
        try:
            result = subprocess.run(["docker", *map(str, args)], stdin=subprocess.DEVNULL,
                                    capture_output=True, timeout=timeout, env=env)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ModelUnavailable("Docker unavailable or command timed out") from exc
        if result.returncode:
            detail = SECRET.sub("[redacted]", result.stderr.decode(errors="replace"))[-1600:]
            raise ModelUnavailable("Docker operation failed: " + detail)
        require(len(result.stdout) <= 4 * 1024 * 1024, "TEMPORARILY_UNAVAILABLE", "도구 출력 한도를 초과했습니다.", 503)
        return result.stdout.decode()

    def runtime(self):
        try:
            value = json.loads((self.root / "runtime-image.json").read_text())
            require(bool(re.fullmatch(r"sha256:[a-f0-9]{64}", value["image_id"])), "RUNTIME_UNAVAILABLE", "고정 실행 이미지가 필요합니다.")
            require(value.get("lock_digest") == digest((ROOT / "templates/requests-v1/requirements.lock").read_text()) and
                    value.get("dockerfile_digest") == digest((ROOT / "infra/Dockerfile.runtime").read_text()),
                    "RUNTIME_UNAVAILABLE", "실행 이미지 입력이 바뀌었습니다. 다시 준비하세요.")
            self.docker("image", "inspect", value["image_id"])
            return value["image_id"]
        except (OSError, ValueError, KeyError) as exc:
            raise ModelUnavailable("Prepare the fixed runtime image first") from exc

    def prepare(self):
        base = self.docker("image", "inspect", "python:3.11-alpine", "--format", "{{index .RepoDigests 0}}").strip()
        require(bool(re.fullmatch(r"python@sha256:[a-f0-9]{64}", base)), "RUNTIME_UNAVAILABLE", "고정 Python base digest가 필요합니다.")
        with tempfile.TemporaryDirectory(dir=self.root) as temp:
            iid = Path(temp) / "image-id"
            self.docker("build", "--build-arg", "PYTHON_BASE=" + base, "--iidfile", iid,
                        "-f", ROOT / "infra/Dockerfile.runtime", ROOT, timeout=600)
            image = iid.read_text().strip()
        value = {"image_id": image, "base_digest": base,
                 "lock_digest": digest((ROOT / "templates/requests-v1/requirements.lock").read_text()),
                 "dockerfile_digest": digest((ROOT / "infra/Dockerfile.runtime").read_text())}
        (self.root / "runtime-image.json").write_text(json.dumps(value, indent=2) + "\n")
        return value

    def runtime_reference(self):
        image = self.runtime()
        reference = "lifecycle-runtime:" + image.split(":")[1]
        self.docker("tag", image, reference)
        require(self.docker("image", "inspect", reference, "--format", "{{.Id}}").strip() == image,
                "RUNTIME_UNAVAILABLE", "실행 이미지 참조가 일치하지 않습니다.")
        return reference

    def workspace(self, run_id, spec_id):
        require(all(re.fullmatch(r"[a-f0-9]{32}", part) for part in (run_id, spec_id)), "INVALID_COMMAND", "서버 발급 작업 ID가 필요합니다.", 422)
        path = self.root / "workspaces" / run_id / spec_id
        if not path.exists():
            path.mkdir(parents=True)
            source = ROOT / "templates/requests-v1"
            for directory in ("app_backend", "app_frontend"):
                shutil.copytree(source / directory, path / directory)
            (path / ".dockerignore").write_text("*\n!app_backend/\n!app_backend/**\n!app_frontend/\n!app_frontend/**\n")
        require(not any(p.is_symlink() for p in path.rglob("*")), "FORBIDDEN", "작업 공간에 심볼릭 링크가 있습니다.", 403)
        return path

    def freeze(self, workspace):
        manifest = {str(p.relative_to(workspace)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(workspace.rglob("*")) if p.is_file() and ".git" not in p.parts}
        candidate_id = digest(manifest).split(":")[1]
        candidate = self.root / "candidates" / candidate_id
        if not candidate.exists():
            shutil.copytree(workspace, candidate)
        for name, expected in manifest.items():
            require(hashlib.sha256((candidate / name).read_bytes()).hexdigest() == expected,
                    "TEMPORARILY_UNAVAILABLE", "후보 파일 무결성 실패입니다.", 503)
        env = {"PATH": os.environ.get("PATH", os.defpath), "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
        def git(*args):
            return subprocess.check_output(["git", "-C", str(candidate), *args], env=env, stderr=subprocess.PIPE).decode().strip()
        if not (candidate / ".git").exists():
            git("init", "-b", "candidate")
        try:
            commit = git("rev-parse", "--verify", "HEAD")
        except subprocess.CalledProcessError:
            git("add", "app_backend", "app_frontend", ".dockerignore")
            git("-c", "user.name=Lifecycle", "-c", "user.email=lifecycle@localhost", "-c", "commit.gpgsign=false", "commit", "-m", "Frozen generated candidate")
            commit = git("rev-parse", "HEAD")
        require(not git("status", "--porcelain"), "TEMPORARILY_UNAVAILABLE", "고정 후보의 Git 상태가 변경됐습니다.", 503)
        with tempfile.TemporaryDirectory(dir=self.root) as temp:
            iid = Path(temp) / "image-id"
            self.docker("build", "--network=none", "--build-arg", "RUNTIME_IMAGE=" + self.runtime_reference(),
                        "--iidfile", iid, "-f", ROOT / "infra/Dockerfile.candidate", candidate, timeout=120)
            image = iid.read_text().strip()
        return dict(candidate_id=candidate_id, commit_sha=commit, image_digest=image, manifest=manifest, path=str(candidate))

    @staticmethod
    def limits(name, network="none", tmp_megabytes=32):
        return ["--name", name, "--network", network, "--user", "65534:65534", "--read-only", "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges", "--pids-limit", "64", "--memory", "512m", "--cpus", "1",
                "--tmpfs", f"/tmp:rw,noexec,nosuid,nodev,size={tmp_megabytes}m,mode=1777", "--log-driver", "none"]

    def start_candidate(self, candidate, network, name, data_volume=None):
        volume = data_volume or name + "-data"
        require(bool(re.fullmatch(r"lifecycle-[a-f0-9-]+-data", volume)), "FORBIDDEN", "제품 데이터 볼륨이 필요합니다.", 403)
        args = ["run", "-d", *self.limits(name, network), "--mount", f"type=volume,src={volume},dst=/data"]
        return self.docker(*args, candidate["image_digest"]).strip()

    def cleanup(self, name):
        require(bool(re.fullmatch(r"lifecycle-[a-f0-9-]+", name)), "FORBIDDEN", "제품이 만든 컨테이너만 정리할 수 있습니다.", 403)
        try:
            self.docker("rm", "-f", name)
        except ModelUnavailable:
            pass
        try:
            return name not in self.docker("ps", "-a", "--format", "{{.Names}}").splitlines()
        except ModelUnavailable:
            return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "status"])
    args = parser.parse_args()
    sandbox = Sandbox(ROOT / "runtime-data")
    print(json.dumps(sandbox.prepare() if args.action == "prepare" else {"image_id": sandbox.runtime()}, indent=2))
