"""Protected reviewers execute outside the candidate, with no shared reports."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile

from backend.contracts import ROOT, digest, require
from backend.store import uid
from runner.model import ModelUnavailable
from runner.sandbox import Sandbox

REVIEW_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["summary", "acceptance"], "properties": {
    "summary": {"type": "string", "maxLength": 2000},
    "acceptance": {"type": "array", "items": {"type": "object", "additionalProperties": False,
        "required": ["id", "status", "evidence"], "properties": {"id": {"type": "string"},
        "status": {"enum": ["met", "failed", "not_run"]}, "evidence": {"type": "array", "items": {"type": "string"}}}}}}}


def scan_covered(report, scanner):
    descriptor = report["descriptor"]
    providers = descriptor["db"]["providers"]
    return (report["source"]["type"] == "image" and descriptor["name"] == "grype" and
            descriptor["version"] == scanner["version"] and descriptor["db"]["status"]["valid"] is True and
            report["distro"]["name"] in providers and "github" in providers and
            all(m["vulnerability"]["severity"].casefold() in ("negligible", "low", "medium", "high", "critical") for m in report["matches"]))


class Reviewer:
    def __init__(self, engine, current=lambda: True):
        self.engine, self.current = engine, current

    def check_current(self):
        if not self.current():
            raise ModelUnavailable("Attempt superseded")

    def validation(self, candidate):
        network, app, checker = ("lifecycle-" + uid() for _ in range(3))
        checks = ROOT / "infra/checks"
        try:
            self.check_current()
            self.engine.docker("network", "create", "--internal", network)
            self.engine.start_candidate(candidate, network, app)
            def check(mode, *args):
                self.check_current()
                return json.loads(self.engine.docker("run", "--rm", *self.engine.limits(checker, network),
                    "--mount", f"type=bind,src={checks},dst=/checks,readonly", self.engine.runtime(),
                    "python", "/checks/validate.py", "http://" + app + ":8080", mode, *args))
            exercise = check("exercise")
            self.check_current()
            self.engine.docker("restart", app)
            persistence = check("persist", str(exercise.get("item_id")))
            return dict(checks={**exercise["checks"], **persistence["checks"]}, exercise=exercise, persistence=persistence,
                        verifier_digest=digest((checks / "validate.py").read_text()))
        finally:
            self.engine.cleanup(app)
            self.engine.cleanup(checker)
            try:
                self.engine.docker("network", "rm", network)
            except ModelUnavailable:
                pass

    def prepare_scanner(self):
        image = self.engine.docker("image", "inspect", "anchore/grype:v0.121.0", "--format", "{{.Id}}").strip()
        cache = self.engine.root / "grype-db"
        cache.mkdir(mode=0o700, exist_ok=True)
        name = "lifecycle-" + uid()
        args = ["run", "--rm", *self.engine.limits(name, "bridge", 512), "--memory", "1g", "--user", f"{os.getuid()}:{os.getgid()}",
                "--mount", f"type=bind,src={cache},dst=/db", "-e", "GRYPE_DB_CACHE_DIR=/db", "-e", "HOME=/tmp"]
        self.engine.docker(*args, image, "db", "update", timeout=600)
        status = json.loads(self.engine.docker(*args, image, "db", "status", "-o", "json"))
        result = dict(image_id=image, version="0.121.0", database=status, prepared_at=datetime.now(timezone.utc).isoformat())
        (self.engine.root / "scanner.json").write_text(json.dumps(result, indent=2) + "\n")
        return result

    def security(self, candidate):
        name = "lifecycle-" + uid()
        checks = ROOT / "infra/checks"
        try:
            self.check_current()
            value = json.loads(self.engine.docker("run", *self.engine.limits(name),
                "--mount", f"type=bind,src={checks},dst=/checks,readonly",
                "--mount", f"type=bind,src={candidate['path']},dst=/candidate,readonly", self.engine.runtime(), "python", "/checks/security.py"))
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
                raw = self.engine.docker("run", "--rm", *self.engine.limits("lifecycle-" + uid(), "none", 512), "--memory", "1536m",
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
