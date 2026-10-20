"""Local contract/queue checks; fake model output is never a LIVE execution claim."""

import asyncio
import copy
import sqlite3
import tempfile
import unittest
import subprocess
import sys
import time
from unittest.mock import patch
from pathlib import Path

from fastapi.testclient import TestClient

from backend.api import create_app
from backend.config import Settings
from backend.contracts import digest, validate
from backend.store import Store, uid
from runner.model import ModelUnavailable
from runner.worker import Worker

ORIGIN = "http://127.0.0.1:5173"
PLAN = dict(goal="작은 문의 앱", features=["문의 목록"], non_goals=["결제"], constraints=["무료만"],
            assumptions=["합성 데이터"], changes=[], acceptance=[dict(id="APP01", title="목록", description="문의 목록이 보인다")])


class FakeModel:
    async def status(self):
        return "ready"

    async def generate(self, packet, schema):
        return copy.deepcopy(PLAN)


class RuntimeChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = Settings(Path(self.temp.name) / "state.sqlite3", "t" * 32)
        self.store = Store(self.settings.database)
        self.worker = Worker(self.store, FakeModel())
        self.client = self.enterContext(TestClient(create_app(self.settings, self.store, FakeModel()),
                                                 base_url="http://127.0.0.1:8000", client=("127.0.0.1", 12345)))
        response = self.client.post("/api/session", json={}, headers={"Origin": ORIGIN})
        self.assertEqual(response.status_code, 201)
        validate("Session", response.json())
        self.headers = {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}

    def live(self):
        self.assertTrue(self.worker.heartbeat())
        project = self.client.post("/api/projects", json={"title": "검사용 합성", "request": "문의 목록을 만든다"}, headers=self.headers)
        self.assertEqual(project.status_code, 201)
        validate("Project", project.json())
        result = self.client.post(f"/api/projects/{project.json()['project_id']}/runs", json={"mode": "live"}, headers=self.headers)
        self.assertEqual(result.status_code, 201, result.text)
        validate("Snapshot", result.json())
        return result.json()

    def command(self, snapshot, action, payload=None):
        return dict(kind="command", protocol_version=1, command_id=uid(), run_id=snapshot["run_id"],
                    expected_state_version=snapshot["state_version"], action=action, payload=payload or {})

    def post_command(self, value):
        return self.client.post(f"/api/runs/{value['run_id']}/commands", json=value, headers=self.headers)

    def planned(self):
        snapshot = self.live()
        self.assertTrue(asyncio.run(self.worker.tick()))
        return self.store.snapshot(snapshot["run_id"])

    def test_auth_csrf_origin_and_logout(self):
        self.assertIn("HttpOnly", self.client.post("/api/session", headers={"Origin": ORIGIN}).headers["set-cookie"])
        self.assertEqual(self.client.post("/api/projects", json={}, headers={"Origin": ORIGIN}).status_code, 403)
        self.assertEqual(self.client.get("/api/runtime", headers={"Origin": "https://hostile.invalid"}).status_code, 403)
        self.assertEqual(self.client.get("/api/runtime", headers={"Host": "hostile.invalid"}).status_code, 403)
        session = self.client.get("/api/session").json()
        self.assertEqual(self.client.delete("/api/session", headers={"Origin": ORIGIN, "X-CSRF-Token": session["csrf_token"]}).status_code, 204)
        self.assertEqual(self.client.get("/api/runtime").status_code, 401)

    def test_packaged_same_origin_static_office_and_separate_cookie(self):
        root = Path(self.temp.name) / "package"
        static = root / "frontend/dist"
        static.mkdir(parents=True)
        (static / "index.html").write_text("<main>synthetic office build</main>")
        with patch("backend.api.ROOT", root):
            app = create_app(self.settings, self.store, FakeModel())
        with TestClient(app, base_url="http://127.0.0.1:8016", client=("127.0.0.1", 12345)) as client:
            self.assertEqual(client.get("/").status_code, 200)
            self.assertIn("synthetic office build", client.get("/").text)
            opened = client.post("/api/session", json={}, headers={"Origin": "http://127.0.0.1:8016"})
            self.assertEqual(opened.status_code, 201)
            self.assertIn("lifecycle_session_8016=", opened.headers["set-cookie"])
            self.assertEqual(client.get("/api/session").status_code, 200)
            self.assertEqual(client.get("/api/runtime", headers={"Origin": "http://127.0.0.1:8017"}).status_code, 403)
            self.assertEqual(client.get("/api/runtime", headers={"Host": "attacker.invalid:8016"}).status_code, 403)

    def test_boundary_and_unavailable_runtime(self):
        value = self.client.get("/api/runtime").json()
        validate("Runtime", value)
        self.assertFalse(value["live_available"])
        for body in ({"title": "x", "request_text": "y"}, {"title": "x", "request": "ghp_" + "a" * 30}):
            result = self.client.post("/api/projects", json=body, headers=self.headers)
            self.assertEqual(result.status_code, 422)
            validate("Error", result.json())
        self.assertEqual(self.client.post("/api/projects", content=b"x" * 131073, headers=self.headers).status_code, 413)
        validate("Error", self.client.get("/api/absent").json())

    def test_plan_approval_idempotency_and_version_conflict(self):
        snapshot = self.planned()
        self.assertEqual(snapshot["state"], "awaiting_plan_approval")
        plan = self.client.get("/api/artifacts/" + next(a["id"] for a in snapshot["artifacts"] if a["kind"] == "spec")).json()
        validate("PlanView", plan)
        approval = snapshot["approvals"][-1]
        self.assertEqual(approval["target"]["plan_digest"], digest(plan))
        decide = self.command(snapshot, "decide", dict(approval_id=approval["id"], target_digest=approval["target_digest"], decision="approve"))
        response = self.post_command(decide)
        self.assertEqual(response.status_code, 202, response.text)
        validate("CommandReceipt", response.json())
        self.assertEqual(self.post_command(decide).json(), response.json())
        other = self.command(snapshot, "pause")
        conflict = self.post_command(other)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["error"]["current_state_version"], snapshot["state_version"] + 1)
        decide["payload"]["decision"] = "reject"
        self.assertEqual(self.post_command(decide).json()["error"]["code"], "COMMAND_CONFLICT")
        asyncio.run(self.worker.tick())
        self.assertEqual(self.store.snapshot(snapshot["run_id"])["state"], "waiting_resource")

    def test_pause_fences_late_result_and_resume(self):
        snapshot = self.live()
        job = self.worker.claim()
        self.assertEqual(self.post_command(self.command(snapshot, "pause")).status_code, 202)
        self.assertFalse(self.worker.finish(job, PLAN))
        paused = self.store.snapshot(snapshot["run_id"])
        self.assertEqual(paused["state"], "paused")
        self.assertFalse(paused["artifacts"])
        self.assertEqual(self.post_command(self.command(paused, "resume")).status_code, 202)
        asyncio.run(self.worker.tick())
        self.assertEqual(self.store.snapshot(snapshot["run_id"])["state"], "awaiting_plan_approval")

    def test_lease_takeover_recovery_and_single_owner(self):
        snapshot = self.live()
        old_job = self.worker.claim()
        replacement = Worker(self.store, FakeModel())
        self.assertFalse(replacement.heartbeat())
        with self.store.transaction() as db:
            db.execute("UPDATE worker_lock SET expires=0")
        self.assertTrue(replacement.heartbeat())
        self.assertFalse(self.worker.finish(old_job, PLAN))
        asyncio.run(replacement.tick())
        self.assertEqual(self.store.snapshot(snapshot["run_id"])["state"], "awaiting_plan_approval")

    def test_replay_frozen_events_readonly_and_cursor_resync(self):
        original = self.planned()
        response = self.client.get("/api/replays")
        validate("ReplayRecordings", response.json())
        replay = self.store.create_run(original["project_id"], {"mode": "replay", "source_run_id": original["run_id"]})
        self.assertEqual(replay["replay_source"]["manifest_digest"], response.json()[0]["manifest_digest"])
        self.assertEqual(self.client.get("/api/replays").json(), response.json())
        self.assertEqual(replay["replay_source"]["recorded_at"], response.json()[0]["recorded_at"])
        original_events = self.store.events(original["run_id"], 0)
        self.assertEqual(response.json()[0]["recorded_at"], original_events[-1]["occurred_at"])
        replay_events = self.store.events(replay["run_id"], 0)
        self.assertEqual([e["occurred_at"] for e in original_events], [e["occurred_at"] for e in replay_events])
        for event in replay_events:
            validate("Event", event)
        self.assertEqual(self.post_command(self.command(replay, "pause")).json()["error"]["code"], "REPLAY_READ_ONLY")
        self.post_command(self.command(original, "pause"))
        self.assertEqual(self.store.snapshot(replay["run_id"]), replay)
        self.assertIn("event: resync", self.client.get(f"/api/runs/{replay['run_id']}/events?after=99999").text)
        self.assertEqual(self.client.get(f"/api/runs/{replay['run_id']}/events?after=bad").status_code, 422)

    def test_same_owner_expired_attempt_cannot_publish_after_reclaim(self):
        snapshot = self.live()
        old = self.worker.claim()
        with self.store.transaction() as db:
            db.execute("UPDATE worker_lock SET expires=0")
        self.assertTrue(self.worker.heartbeat())
        fresh = self.worker.claim()
        self.assertEqual(old["id"], fresh["id"])
        self.assertNotEqual(old["attempt_id"], fresh["attempt_id"])
        self.assertFalse(self.worker.current(old))
        with self.store.transaction() as db:
            self.assertIsNone(self.worker.pipeline.valid(db, old, self.worker))
        self.assertFalse(self.worker.finish(old, PLAN))
        self.assertTrue(self.worker.current(fresh))
        self.assertTrue(self.worker.finish(fresh, PLAN))
        self.assertEqual(self.store.snapshot(snapshot["run_id"])["state"], "awaiting_plan_approval")

    def test_process_exit_leaves_durable_job_for_lease_successor(self):
        project = self.store.project(dict(title="synthetic restart", request="문의 목록"))
        snapshot = self.store.create_run(project["project_id"], dict(mode="live"))
        script = "from pathlib import Path; import sys; from backend.store import Store; from runner.worker import Worker; w=Worker(Store(Path(sys.argv[1])),None); assert w.heartbeat(); assert w.claim()"
        subprocess.run([sys.executable, "-c", script, str(self.store.path)], check=True, timeout=15)
        self.assertFalse(self.worker.heartbeat())
        with self.store.transaction() as db:
            expires = db.execute("SELECT expires FROM worker_lock").fetchone()[0]
            self.assertEqual(db.execute("SELECT state FROM jobs").fetchone()[0], "running")
        time.sleep(max(0, expires - time.time()) + .02)
        self.assertTrue(self.worker.heartbeat())
        job = self.worker.claim()
        self.assertEqual(job["run_id"], snapshot["run_id"])
        self.assertTrue(self.worker.finish(job, PLAN))
        with self.store.transaction() as db:
            self.assertEqual([r[0] for r in db.execute("SELECT outcome FROM attempt_results ORDER BY rowid")], ["superseded", "finished"])

    def test_corrupt_artifact_is_contract_error(self):
        snapshot = self.live()
        for content, metadata in (("{", "{}"), ("{}", "null"), ("{}", "{}")):
            artifact_id = uid()
            with self.store.transaction() as db:
                db.execute("INSERT INTO artifacts VALUES (?, ?, ?, ?, 1)",
                           (artifact_id, snapshot["run_id"], metadata, content))
            response = self.client.get("/api/artifacts/" + artifact_id)
            self.assertEqual(response.status_code, 503)
            validate("Error", response.json())

    def test_replan_preserves_feedback_and_immutable_records(self):
        before = self.planned()
        request = self.command(before, "request_changes", {"scope": "spec", "feedback": "문의 상세도 추가"})
        self.assertEqual(self.post_command(request).status_code, 202)
        job = self.worker.claim()
        self.assertEqual(job["packet"]["requests"][-1]["content"], "문의 상세도 추가")
        self.assertEqual(job["packet"]["latest_spec"]["goal"], PLAN["goal"])
        self.worker.finish(job, PLAN)
        after = self.store.snapshot(before["run_id"])
        self.assertNotEqual(after["spec_version_id"], before["spec_version_id"])
        self.assertEqual(after["approvals"][0]["state"], "invalidated")
        with self.assertRaises(sqlite3.IntegrityError), self.store.transaction() as db:
            db.execute("DELETE FROM requests")

    def test_model_unavailable_never_becomes_pass(self):
        class Missing(FakeModel):
            async def generate(self, packet, schema):
                raise ModelUnavailable()
        snapshot = self.live()
        self.worker.model = Missing()
        asyncio.run(self.worker.tick())
        result = self.store.snapshot(snapshot["run_id"])
        self.assertEqual(result["state"], "waiting_resource")
        self.assertFalse(result["reports"])
        self.assertFalse(result["approvals"])

    def test_pause_cancels_inflight_model(self):
        snapshot = self.live()
        checks = self

        class Pausing(FakeModel):
            completed = False

            async def generate(self, packet, schema):
                checks.store.command(snapshot["run_id"], checks.command(snapshot, "pause"))
                await asyncio.sleep(10)
                self.completed = True
                return copy.deepcopy(PLAN)

        self.worker.model = Pausing()
        asyncio.run(self.worker.tick())
        self.assertFalse(self.worker.model.completed)
        self.assertFalse(self.store.snapshot(snapshot["run_id"])["artifacts"])

    def test_long_context_is_decomposed_and_preserves_full_request(self):
        from runner.context import fragments
        self.worker.heartbeat()
        project = self.store.project({"title": "long", "request": "가" * 10000})
        snapshot = self.store.create_run(project["project_id"], {"mode": "live"})
        asyncio.run(self.worker.tick())
        self.assertEqual(self.store.snapshot(snapshot["run_id"])["state"], "awaiting_plan_approval")
        with self.store.transaction() as db:
            self.assertEqual(len(db.execute("SELECT content FROM requests").fetchone()[0]), 10000)
            self.assertGreater(db.execute("SELECT COUNT(*) FROM context_steps").fetchone()[0], 1)
            requests = [dict(r) for r in db.execute("SELECT * FROM requests")]
        self.assertEqual("".join(p["text"] for p in fragments(requests)), "가" * 10000)

    def test_planning_resumes_checkpoint_and_retains_mandatory_conditions(self):
        from runner.context import BUDGET
        from backend.contracts import canonical
        calls = []
        class Interrupted(FakeModel):
            broken = True
            async def generate(self, packet, schema):
                calls.append(copy.deepcopy(packet))
                if len(calls) == 2 and self.broken:
                    raise ModelUnavailable()
                return copy.deepcopy(PLAN)
        self.worker.model = Interrupted()
        self.worker.heartbeat()
        project = self.store.project({"title": "long", "request": "원래 조건 " * 1000})
        snapshot = self.store.create_run(project["project_id"], {"mode": "live"})
        asyncio.run(self.worker.tick())
        waiting = self.store.snapshot(snapshot["run_id"])
        self.assertEqual(waiting["state"], "waiting_resource")
        self.worker.model.broken = False
        self.post_command(self.command(waiting, "resume"))
        asyncio.run(self.worker.tick())
        self.assertEqual(self.store.snapshot(snapshot["run_id"])["state"], "awaiting_plan_approval")
        self.assertEqual(sum(c["fragment_index"] == 0 for c in calls), 1)
        self.assertTrue(calls[2]["unresolved_failures"])
        self.assertTrue(all(len(canonical(c).encode()) <= BUDGET for c in calls))
        self.assertEqual(calls[2]["accumulated_plan"]["constraints"], PLAN["constraints"])

    def test_sse_serialized_event_matches_contract(self):
        import json
        from types import SimpleNamespace

        snapshot = self.planned()
        route = next(r for r in self.client.app.routes if r.path == "/api/runs/{run_id}/events")

        class Request:
            headers = {}
            app = self.client.app
            state = SimpleNamespace()
            calls = 0

            async def is_disconnected(self):
                self.calls += 1
                return self.calls > 1

        async def collect():
            response = await route.endpoint(snapshot["run_id"], Request(), "0")
            return [chunk async for chunk in response.body_iterator]

        chunks = asyncio.run(collect())
        self.assertEqual(len(chunks), snapshot["last_event_seq"])
        for chunk in chunks:
            validate("Event", json.loads(chunk.split("data: ", 1)[1]))

    def test_build_requires_current_approved_plan(self):
        snapshot = self.live()
        with self.store.transaction() as db:
            snapshot["state"] = "building"
            self.store.save(db, snapshot, "run_state_changed", "검사용 비정상 상태")
            self.store.schedule(db, snapshot, "builder")
        asyncio.run(self.worker.tick())
        self.assertEqual(self.store.snapshot(snapshot["run_id"])["state"], "needs_input")

    def test_duplicate_acceptance_ids_cannot_be_approved(self):
        class Duplicate(FakeModel):
            async def generate(self, packet, schema):
                plan = copy.deepcopy(PLAN)
                plan["acceptance"] *= 2
                return plan
        snapshot = self.live()
        self.worker.model = Duplicate()
        asyncio.run(self.worker.tick())
        result = self.store.snapshot(snapshot["run_id"])
        self.assertEqual(result["state"], "needs_input")
        self.assertFalse(result["approvals"])


if __name__ == "__main__":
    unittest.main()
