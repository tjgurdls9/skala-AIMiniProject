"""Fixed Docker operations. Model output never becomes a shell command or mount."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from backend.contracts import ROOT, SECRET, digest, require
from backend.templates import template_path
from runner.model import ModelUnavailable


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
            require(value.get("dockerfile_digest") == digest((ROOT / "infra/Dockerfile.runtime").read_text()),
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
                 "dockerfile_digest": digest((ROOT / "infra/Dockerfile.runtime").read_text())}
        (self.root / "runtime-image.json").write_text(json.dumps(value, indent=2) + "\n")
        return value

    def workspace(self, run_id, spec_id, template_id):
        require(all(re.fullmatch(r"[a-f0-9]{32}", part) for part in (run_id, spec_id)), "INVALID_COMMAND", "서버 발급 작업 ID가 필요합니다.", 422)
        path = self.root / "workspaces" / run_id / spec_id
        if not path.exists():
            template_path(template_id)   # a starter ships no feature code: the workspace begins empty and the model authors everything
            path.mkdir(parents=True)
        require(not any(p.is_symlink() for p in path.rglob("*")), "FORBIDDEN", "작업 공간에 심볼릭 링크가 있습니다.", 403)
        return path

    @staticmethod
    def limits(name, network="none", tmp_megabytes=32, memory="512m"):
        return ["--name", name, "--network", network, "--user", "65534:65534", "--read-only", "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges", "--pids-limit", "64", "--memory", memory, "--memory-swap", memory, "--cpus", "1",
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
