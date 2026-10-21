"""Operator check in real containers, no model: commit, freeze offline, then run the approved checks against the image.
The tiny app is deliberately wrong (double(2) returns 2) while the builder-style test defines its own double(), so a test run would be green.
Usage: backend/.venv/bin/python infra/verify_candidate_review.py <python@sha256:...>   Prints one JSON object; exit 1 if a check fails."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "infra/dev_checks"))

import memory_guard  # noqa: E402
from runner.candidate import APP_FILE, commit_task, freeze_model  # noqa: E402
from runner.plan_checks import check_verification  # noqa: E402
from runner.review import Reviewer, model_validation_body  # noqa: E402
from runner.sandbox import Sandbox  # noqa: E402

SERVER = '''import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse
from mathlib import double


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/health":
            body = {"status": "ok"}
        elif url.path == "/double":
            body = {"result": double(int(parse_qs(url.query)["x"][0]))}
        else:
            self.send_response(404)
            self.end_headers()
            return
        raw = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args):
        pass


HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
'''
FILES = {
    "mathlib.py": "def double(x):\n    return x   # wrong on purpose\n",
    "server/main.py": SERVER,
    "server/test_main.py": "import unittest\n\ndef double(x):\n    return x * 2\n\nclass T(unittest.TestCase):\n    def test_double(self):\n        self.assertEqual(double(2), 4)\n",
    APP_FILE: json.dumps(dict(runtime="python", start=["python", "-m", "server.main"], port=8080, health="/health")),
}
CHECKS = [
    dict(id="health", ac_ids=["AC1"], kind="http", steps=[dict(method="GET", path="/health", expect=dict(status=200, json_subset={"status": "ok"}))]),
    dict(id="double-http", ac_ids=["AC2"], kind="http", steps=[dict(method="GET", path="/double?x=2", expect=dict(status=200, json_subset={"result": 4}))]),
    dict(id="double-inline", ac_ids=["AC2"], kind="command", argv=["python", "-c", "from mathlib import double; assert double(2) == 4"], expect=dict(exit=0)),
    dict(id="manifest-file", ac_ids=["AC1"], kind="file", path=APP_FILE, expect=dict(exists=True, contains=["8080"])),
]
UNITTEST_CHECK = dict(id="runs-builder-tests", ac_ids=["AC2"], kind="command", argv=["python", "-m", "unittest"], expect=dict(exit=0))
ACCEPTANCE = [dict(id="AC1", title="상태 확인", description="앱이 시작되고 상태 확인에 응답한다"), dict(id="AC2", title="두 배", description="double(2)가 4를 반환한다")]


def docker(*args):
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=120)


def main(python_image):
    volumes_before = {v for v in docker("volume", "ls", "--format", "{{.Name}}").stdout.split() if v.startswith("lifecycle-")}   # other runs' volumes are not ours
    ok, why = memory_guard.ready_to_start(memory_guard.sample())
    if not ok:
        print(json.dumps(dict(status="not_started", reason=why), ensure_ascii=False))
        return False
    work = Path(tempfile.mkdtemp(prefix="lc-candidate-"))
    workspace = work / "ws"
    for name, text in FILES.items():
        (workspace / name).parent.mkdir(parents=True, exist_ok=True)
        (workspace / name).write_text(text)
    (work / "ws.deps").mkdir()
    engine = Sandbox(work / "engine")
    commit_task(workspace, "task-1", "검증 대상 앱")
    candidate = freeze_model(engine, workspace, work / "ws.deps", python_image)
    results = []

    def check(name, passed, evidence):
        results.append(dict(check=name, ok=bool(passed), evidence=evidence))

    in_image = docker("run", "--rm", candidate["image_digest"], "python", "-c", "import os; print(os.path.exists('/app/server/test_main.py'), os.path.exists('/app/mathlib.py'))")
    check("image_has_the_app_but_not_the_builder_test", in_image.stdout.split() == ["False", "True"], in_image.stdout.strip() or in_image.stderr.strip()[:200])
    check("candidate_checkout_and_history_keep_the_test", "server/test_main.py" in candidate["manifest"] and candidate["excluded_tests"] == ["server/test_main.py"], candidate["excluded_tests"])
    unit = docker("run", "--rm", candidate["image_digest"], "python", "-m", "unittest")
    check("a_test_runner_finds_nothing_to_run_in_the_image", unit.returncode != 0, dict(exit=unit.returncode, tail=unit.stderr.strip()[-120:]))
    rejected = check_verification([UNITTEST_CHECK], [], ACCEPTANCE)
    check("planning_rejects_a_check_that_runs_builder_tests", any("자기 완결" in e for e in rejected), rejected[:1])
    check("planning_accepts_the_inline_checks", check_verification(CHECKS, [], ACCEPTANCE) == [], None)

    outcomes, info = Reviewer(engine).model_validation(candidate, CHECKS, python_image)
    body = model_validation_body(dict(acceptance=ACCEPTANCE, manual_acceptance=[], verification=CHECKS), outcomes, info)
    by_id = {o.id: o.status for o in outcomes}
    check("app_started_and_answered_its_health_path", info["healthy"] and by_id["health"] == "passed", by_id)
    check("the_wrong_implementation_fails_both_http_and_inline_checks", by_id["double-http"] == "failed" and by_id["double-inline"] == "failed", by_id)
    check("the_file_check_passes", by_id["manifest-file"] == "passed", by_id)
    check("report_is_fail_with_AC2_unmet_and_AC1_met", body["verdict"] == "fail" and {a["id"]: a["status"] for a in body["judgement"]["acceptance"]} == {"AC1": "met", "AC2": "unmet"},
          dict(verdict=body["verdict"], acceptance=body["judgement"]["acceptance"]))
    leftovers = docker("ps", "-a", "--filter", "name=lifecycle-", "--format", "{{.Names}}").stdout.split()
    volumes = sorted({v for v in docker("volume", "ls", "--format", "{{.Name}}").stdout.split() if v.startswith("lifecycle-")} - volumes_before)
    check("no_container_network_or_volume_is_left_behind", not leftovers and not volumes, dict(containers=leftovers, volumes=volumes))
    print(json.dumps(dict(status="done", image=python_image, results=results), ensure_ascii=False, indent=1))
    return all(r["ok"] for r in results)


if __name__ == "__main__":
    sys.exit(0 if main(sys.argv[1]) else 1)
