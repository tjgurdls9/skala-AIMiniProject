"""Protected reviewers execute outside the candidate, with no shared reports."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

from backend.contracts import ROOT, DomainError, digest
from backend.store import uid
from runner.check_runner import CheckOutcome, acceptance_verdicts, evaluate
from runner.commands import CommandResult, bounded_run, redact
from runner.model import ModelUnavailable
from runner.sandbox import Sandbox
from runner.workspace import Workspace

def scan_covered(report, scanner):
    descriptor = report["descriptor"]
    providers = descriptor["db"]["providers"]
    return (report["source"]["type"] == "image" and descriptor["name"] == "grype" and
            descriptor["version"] == scanner["version"] and descriptor["db"]["status"]["valid"] is True and
            report["distro"]["name"] in providers and "github" in providers and
            all(m["vulnerability"]["severity"].casefold() in ("negligible", "low", "medium", "high", "critical") for m in report["matches"]))


HEALTH_TRIES, HEALTH_WAIT, PROBE_BODY = 30, 0.5, 4096
INFRASTRUCTURE_CODES = (125, 126, 127)   # docker could not start / invoke / find the program: not a verdict on the app
UNHEALTHY = "앱이 시작되지 않았거나 상태 확인에 응답하지 않았습니다."


def model_validation_body(spec, outcomes, info):
    """The validator report for a model-authored candidate, derived only from executed approved checks."""
    verdicts = acceptance_verdicts(spec["acceptance"], spec.get("verification", []), spec.get("manual_acceptance", []), outcomes)
    pending = [v["id"] for v in verdicts if v["status"] == "not_run" and v["reason"] == "manual"]   # a person confirms these; they stay not_run
    states = {v["status"] for v in verdicts if v["id"] not in pending}
    verdict = ("error" if any(o.status == "error" for o in outcomes) else "fail" if "unmet" in states else
               "not_run" if "not_run" in states else "pass")
    problems = [] if info.get("healthy", True) else [UNHEALTHY]
    summary = " ".join(problems + [f"{sum(v['status'] == 'met' for v in verdicts)}/{len(verdicts)}개 기준이 승인된 점검으로 충족됐습니다."])
    return dict(verdict=verdict, tools=dict(mechanical=True, healthy=info.get("healthy", True),
                                            checks={o.id: o.status == "passed" for o in outcomes},
                                            outcomes=[dict(id=o.id, status=o.status, detail=o.detail, evidence=o.evidence) for o in outcomes]),
                judgement=dict(summary=summary, acceptance=[dict(id=v["id"], status=v["status"], evidence=v["check_ids"]) for v in verdicts]),
                manual_pending=pending)


class CandidateEnv:
    """Where approved checks run: http through a checker container on the internal network, commands inside the candidate image
    (no network), files in the candidate checkout."""
    def __init__(self, reviewer, candidate, network, app, checker_image):
        self.reviewer, self.candidate, self.network, self.app, self.checker_image = reviewer, candidate, network, app, checker_image
        self.checkers = []

    def http(self, method, path, body=None):
        name = "lifecycle-" + uid()
        self.checkers.append(name)
        args = ["run", "--rm", *self.reviewer.engine.limits(name, self.network), "--mount", f"type=bind,src={ROOT / 'infra/checks'},dst=/checks,readonly",
                self.checker_image, "python", "/checks/http_probe.py", f"http://{self.app}:8080", method, path]
        result = json.loads(self.reviewer.engine.docker(*args, *([json.dumps(body)] if body is not None else []), timeout=30))
        if "error" in result:
            raise OSError(result["error"])
        return result["status"], result["body"]

    def run(self, argv, cwd, timeout):
        name = "lifecycle-" + uid()
        self.checkers.append(name)
        workdir = [] if cwd == "." else ["--workdir", f"/app/{cwd}"]
        args = ["docker", "run", "--rm", *self.reviewer.engine.limits(name, "none"), *workdir, self.candidate["image_digest"], *argv]
        try:
            done = self.reviewer.runner(args, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            self.reviewer.engine.cleanup(name)
            return CommandResult(None, "", "", True, False)
        if done.returncode in INFRASTRUCTURE_CODES:
            raise DomainError("RUNTIME_UNAVAILABLE", "격리 컨테이너가 점검 명령을 실행하지 못했습니다: " + redact(done.stderr.decode(errors="replace"))[:200], 503)
        cap = 65536
        return CommandResult(done.returncode, redact(done.stdout[:cap].decode(errors="replace")), redact(done.stderr[:cap].decode(errors="replace")),
                             False, len(done.stdout) > cap or len(done.stderr) > cap)

    def read_text(self, path):
        try:
            return Workspace(Path(self.candidate["path"])).read(path)["content"]
        except DomainError as error:
            if error.code == "NOT_FOUND":
                return None
            raise


class Reviewer:
    def __init__(self, engine, current=lambda: True, runner=bounded_run, sleep=time.sleep):
        self.engine, self.current, self.runner, self.sleep = engine, current, runner, sleep

    def check_current(self):
        if not self.current():
            raise ModelUnavailable("Attempt superseded")

    def model_validation(self, candidate, specs, checker_image):
        """Run the approved check specs against the frozen image; returns (outcomes, {"healthy": bool}). No model is involved."""
        network, app = "lifecycle-" + uid(), "lifecycle-" + uid()
        env = CandidateEnv(self, candidate, network, app, checker_image)
        try:
            self.check_current()
            self.engine.docker("network", "create", "--internal", network)
            self.engine.start_candidate(candidate, network, app)
            healthy = self.wait_healthy(env, candidate["app"]["health"])
            outcomes = []
            for spec in specs:
                self.check_current()
                if spec["kind"] == "http" and not healthy:
                    outcomes.append(CheckOutcome(spec["id"], "failed", UNHEALTHY, dict(healthy=False)))
                else:
                    outcomes.append(evaluate(spec, env))
            return outcomes, dict(healthy=healthy)
        finally:
            for name in [app, *env.checkers]:
                self.engine.cleanup(name)
            for resource in (("network", "rm", network), ("volume", "rm", app + "-data")):   # the validation app's data is throwaway
                try:
                    self.engine.docker(*resource)
                except ModelUnavailable:
                    pass

    def wait_healthy(self, env, path):
        for _ in range(HEALTH_TRIES):
            self.check_current()
            try:
                status, _ = env.http("GET", path)
                if 200 <= status < 400:
                    return True
            except (OSError, ValueError, KeyError):
                pass
            self.sleep(HEALTH_WAIT)
        return False

    def prepare_scanner(self):
        image = self.engine.docker("image", "inspect", "anchore/grype:v0.121.0", "--format", "{{.Id}}").strip()
        cache = self.engine.root / "grype-db"
        cache.mkdir(mode=0o700, exist_ok=True)
        name = "lifecycle-" + uid()
        args = ["run", "--rm", *self.engine.limits(name, "bridge", 512, "1g"), "--user", f"{os.getuid()}:{os.getgid()}",
                "--mount", f"type=bind,src={cache},dst=/db", "-e", "GRYPE_DB_CACHE_DIR=/db", "-e", "HOME=/tmp"]
        self.engine.docker(*args, image, "db", "update", timeout=600)
        status = json.loads(self.engine.docker(*args, image, "db", "status", "-o", "json"))
        result = dict(image_id=image, version="0.121.0", database=status, prepared_at=datetime.now(timezone.utc).isoformat())
        (self.engine.root / "scanner.json").write_text(json.dumps(result, indent=2) + "\n")
        return result

    def security(self, candidate, checker_image, approved_dependencies=None):
        name = "lifecycle-" + uid()
        checks = ROOT / "infra/checks"
        # allow only what the approved dependencies provide, resolved from the installed distributions
        known = candidate.get("dependency_modules", {})
        approved = [re.sub(r"[-_.]+", "-", d.split("==")[0]).lower() for d in (approved_dependencies or {}).get("pip", [])]
        command = ["python", "/checks/security.py", "--model-authored", ",".join(sorted({m for d in approved for m in known.get(d, [])})),
                   "--unverified", ",".join(d for d in approved if d not in known)]
        try:
            self.check_current()
            value = json.loads(self.engine.docker("run", *self.engine.limits(name),
                "--mount", f"type=bind,src={checks},dst=/checks,readonly",
                "--mount", f"type=bind,src={candidate['path']},dst=/candidate,readonly", checker_image, *command))
            inspect = json.loads(self.engine.docker("inspect", name))[0]
            host = inspect["HostConfig"]
            value["checks"]["isolation"] = (host["ReadonlyRootfs"] and not host["Privileged"] and
                host["NetworkMode"] == "none" and "ALL" in host["CapDrop"] and inspect["Config"]["User"] == "65534:65534" and
                all(m["Destination"] in ("/checks", "/candidate") and not m["RW"] for m in inspect["Mounts"]))
            value["verifier_digest"] = digest((checks / "security.py").read_text())
            scanner_file = self.engine.root / "scanner.json"
            if not scanner_file.exists():
                return {**value, "verdict": "not_run", "reason": "고정 취약점 스캐너/DB 준비가 필요합니다."}
            scanner = json.loads(scanner_file.read_text())
            with tempfile.TemporaryDirectory(dir=self.engine.root) as temp:
                image_tar = Path(temp) / "candidate.tar"
                self.check_current()
                self.engine.docker("save", "--output", image_tar, candidate["image_digest"], timeout=120)
                image_tar.chmod(0o644)
                self.check_current()
                raw = self.engine.docker("run", "--rm", *self.engine.limits("lifecycle-" + uid(), "none", 512, "1536m"),
                    "--user", f"{os.getuid()}:{os.getgid()}",
                    "--mount", f"type=bind,src={image_tar},dst=/scan/candidate.tar,readonly",
                    "--mount", f"type=bind,src={self.engine.root / 'grype-db'},dst=/db,readonly",
                    "-e", "GRYPE_DB_CACHE_DIR=/db", "-e", "GRYPE_DB_AUTO_UPDATE=false", "-e", "GRYPE_CHECK_FOR_APP_UPDATE=false",
                    "-e", "GRYPE_DB_VALIDATE_AGE=true", "-e", "GRYPE_DB_MAX_ALLOWED_BUILT_AGE=168h", "-e", "HOME=/tmp",
                    scanner["image_id"], "docker-archive:/scan/candidate.tar", "-o", "json", timeout=180)
                report = json.loads(raw)
            blocking = [m for m in report["matches"] if m["vulnerability"]["severity"].casefold() in ("high", "critical")]
            value["checks"]["scanner_coverage"] = scan_covered(report, scanner)
            value["checks"]["dependency_image"] = not blocking
            value["scanner"] = scanner
            value["vulnerability_report"] = report
            value["verdict"] = "pass" if all(value["checks"].values()) else "fail"
            return value
        finally:
            self.engine.cleanup(name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare-scanner"])
    parser.parse_args()
    print(json.dumps(Reviewer(Sandbox(ROOT / "runtime-data")).prepare_scanner(), indent=2))
