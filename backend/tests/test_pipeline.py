"""Synthetic orchestration checks; mocked tools never represent product review PASS."""
import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from backend.contracts import DomainError, canonical, digest
from runner.access import RoleScope, issue_grant
from runner.check_runner import CheckOutcome
from runner.pipeline import Pipeline
from runner.review import Reviewer, scan_covered
from runner.worker import Worker, failure_reason
from runner.model import ModelUnavailable, sampling_schema
import test_runtime as fixtures


IMAGES = dict(python="python@sha256:" + "a" * 64, node="node@sha256:" + "b" * 64)


class PipelineChecks(unittest.TestCase):
    def setUp(self):
        fixtures.RuntimeChecks.setUp(self)
        self.worker.pipeline.executor = SimpleNamespace(images=IMAGES)   # the digest-pinned tool images; Docker is never started here

    live = fixtures.RuntimeChecks.live
    planned = fixtures.RuntimeChecks.planned
    command = fixtures.RuntimeChecks.command
    post_command = fixtures.RuntimeChecks.post_command

    def approved(self):
        snapshot = self.planned()
        approval = snapshot["approvals"][-1]
        result = self.post_command(self.command(snapshot, "decide", dict(approval_id=approval["id"], target_digest=approval["target_digest"], decision="approve")))
        self.assertEqual(result.status_code, 202)
        return self.store.snapshot(snapshot["run_id"])

    def built(self, snapshot=None, health="/health"):
        snapshot = snapshot or self.approved()
        job = self.worker.claim()
        workspace = self.worker.pipeline.engine.workspace(job["run_id"], snapshot["spec_version_id"], "blank-v1")
        candidate = dict(commit_sha="a" * 40, image_digest="sha256:" + "b" * 64, manifest={}, path=str(workspace), app=dict(runtime="python", health=health))
        with patch.object(Pipeline, "model_edit", new=AsyncMock()), patch("runner.pipeline.commit_task", return_value="a" * 40), \
             patch("runner.pipeline.freeze_model", return_value=candidate):
            while job is not None:
                asyncio.run(self.worker.pipeline.build(job, self.worker))
                if self.store.snapshot(snapshot["run_id"])["state"] != "building":
                    break
                job = self.worker.claim()
        return self.store.snapshot(snapshot["run_id"])

    def validator(self):
        """The approved checks decide; the planned check for APP01 is reported as passed."""
        with patch.object(Reviewer, "model_validation", return_value=([CheckOutcome("APP01-1", "passed", "", {})], dict(healthy=True))):
            asyncio.run(self.worker.tick())

    def test_pending_review_hidden_and_not_run_blocks_preview(self):
        before = self.built()
        self.validator()
        hidden = self.store.snapshot(before["run_id"])
        self.assertEqual(hidden, before)
        pending = self.client.get(f"/api/runs/{before['run_id']}/acceptance").json()
        self.assertEqual(pending["items"], [{"id": "APP01", "status": "unmet"}])
        with self.store.transaction() as db:
            row = db.execute("SELECT context FROM jobs WHERE role='security'").fetchone()
            self.assertNotIn("judgement", row[0])
        with patch.object(Reviewer, "security", return_value={"verdict": "not_run", "checks": {}}):
            asyncio.run(self.worker.tick())
        after = self.store.snapshot(before["run_id"])
        self.assertEqual(after["state"], "waiting_resource")
        self.assertEqual({r["verdict"] for r in after["reports"]}, {"pass", "not_run"})
        self.assertFalse(any(a["kind"] == "preview" for a in after["artifacts"]))
        published = self.store.acceptance_status(before["run_id"])
        self.assertEqual(published["items"][0]["status"], "met")
        self.assertEqual(published["items"][0]["report_id"], next(r["id"] for r in after["reports"] if r["role"] == "validator"))
        replay = self.store.create_run(before["project_id"], {"mode": "replay", "source_run_id": before["run_id"]})
        self.assertEqual(self.store.acceptance_status(replay["run_id"]), published)

    def test_implementation_dag_follows_the_approved_work_plan(self):
        snapshot = self.approved()
        builders = [t for t in snapshot["tasks"] if t["role"] == "builder"]
        planner = next(t for t in snapshot["tasks"] if t["role"] == "planner")
        self.assertEqual([t["work_kind"] for t in builders], ["backend", "frontend"])
        self.assertEqual([t["depends_on"] for t in builders], [[planner["id"]], [builders[0]["id"]]])
        with patch.object(Pipeline, "model_edit", new=AsyncMock()), patch("runner.pipeline.commit_task", return_value="a" * 40):
            asyncio.run(self.worker.tick())
        job = self.worker.claim()
        self.assertEqual(job["packet"]["options"]["task_id"], builders[1]["id"])
        self.assertEqual(job["packet"]["options"]["write_scope"], ["web/**"])
        with self.store.transaction() as db:
            task = next(t for t in self.store.load(db, snapshot["run_id"])["tasks"] if t["id"] == builders[0]["id"])
            self.assertEqual(task["state"], "succeeded")
            self.assertEqual(len(db.execute("SELECT * FROM candidates").fetchall()), 0)

    def test_review_same_candidate_gate_and_every_change_request_replans(self):
        before = self.built()
        self.validator()
        with patch.object(Reviewer, "security", return_value={"verdict": "pass", "checks": {"synthetic": True}}):
            asyncio.run(self.worker.tick())
        ready = self.store.snapshot(before["run_id"])
        self.assertEqual(ready["state"], "preview_ready")
        job = self.worker.claim()
        with self.store.transaction() as db:
            changed = self.store.load(db, ready["run_id"])
            changed["reports"][0]["commit_sha"] = "c" * 40
            db.execute("UPDATE runs SET snapshot=? WHERE id=?", (canonical(changed), ready["run_id"]))
        with self.assertRaises(DomainError):
            asyncio.run(self.worker.pipeline.release(job, self.worker))
        with self.store.transaction() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM operations").fetchone()[0], 0)
            db.execute("UPDATE runs SET snapshot=? WHERE id=?", (canonical(ready), ready["run_id"]))
        response = self.post_command(self.command(ready, "request_changes", {"scope": "implementation", "feedback": "화면 배치를 바꿔 주세요"}))
        self.assertEqual(response.status_code, 202, response.text)
        replanned = self.store.snapshot(ready["run_id"])
        self.assertEqual(replanned["state"], "planning")      # no wording is treated as a small change that may reuse the old approval
        self.assertIsNone(replanned["spec_version_id"])
        self.assertTrue(all(a["state"] == "invalidated" for a in replanned["approvals"]))
        self.assertTrue(self.store.read_artifact(ready["reports"][0]["artifact_id"]))  # Old evidence remains historical.

    def test_old_mcp_grant_denied_after_lease_takeover(self):
        snapshot = self.approved()
        job = self.worker.claim()
        token = issue_grant(self.store, job)
        replacement = Worker(self.store, fixtures.FakeModel())
        with self.store.transaction() as db:
            db.execute("UPDATE worker_lock SET expires=0")
        replacement.heartbeat()
        self.assertIsNotNone(replacement.claim())
        with self.assertRaises(DomainError):
            RoleScope(self.store, token).resource("spec")

    def test_sampling_keeps_server_schema_and_enums(self):
        schema = {"type": "object", "properties": {"path": {"enum": ["a", "b"]}, "content": {"type": "string", "maxLength": 65536}}}
        sampled = sampling_schema(schema)
        self.assertNotIn("maxLength", canonical(sampled))
        self.assertEqual(schema["properties"]["content"]["maxLength"], 65536)
        self.assertEqual(sampled["properties"]["path"], schema["properties"]["path"])
        self.assertEqual(failure_reason(ExceptionGroup("stdio", [ModelUnavailable()]))[0], "waiting_resource")

    def test_stale_review_cannot_publish(self):
        before = self.built()
        job = self.worker.claim()
        self.post_command(self.command(before, "pause"))
        with patch.object(Reviewer, "model_validation", return_value=([CheckOutcome("APP01-1", "passed", "", {})], dict(healthy=True))):
            asyncio.run(self.worker.pipeline.review(job, self.worker))
        self.assertEqual(self.store.snapshot(before["run_id"])["state"], "paused")
        with self.store.transaction() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM reviews").fetchone()[0], 0)

    def test_changed_protected_inputs_reject_old_approval(self):
        snapshot = self.planned()
        approval = snapshot["approvals"][-1]
        with patch("backend.store.plan_inputs", return_value={"changed": "sha256:" + "0" * 64}):
            response = self.post_command(self.command(snapshot, "decide", dict(approval_id=approval["id"], target_digest=approval["target_digest"], decision="approve")))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "STALE_APPROVAL")
        self.assertEqual(self.store.snapshot(snapshot["run_id"])["state"], "awaiting_plan_approval")

    def test_empty_scan_needs_known_distro_and_valid_database(self):
        report = dict(source={"type": "image"}, distro={"name": "alpine"}, matches=[],
                      descriptor=dict(name="grype", version="test", db={"providers": {"alpine": {}, "github": {}}, "status": {"valid": True}}))
        scanner = {"version": "test"}
        self.assertTrue(scan_covered(report, scanner))
        report["distro"]["name"] = "unknown"
        self.assertFalse(scan_covered(report, scanner))
        report["distro"]["name"] = "alpine"
        report["matches"] = [{"vulnerability": {"severity": "Unknown"}}]
        self.assertFalse(scan_covered(report, scanner))

    def test_new_preview_preserves_same_spec_volume_and_retires_old_service(self):
        snapshot = self.approved()
        old_key = "sha256:" + "d" * 64
        old = dict(app="lifecycle-" + "a" * 32, proxy="lifecycle-" + "b" * 32, network="lifecycle-" + "c" * 32)
        with self.store.transaction() as db:
            db.execute("INSERT INTO candidates VALUES (?, ?, ?, ?)", (old_key, snapshot["run_id"], snapshot["spec_version_id"], "{}"))
            db.execute("INSERT INTO previews VALUES (?, ?, ?)", (snapshot["run_id"], old_key, canonical(old)))
            db.execute("INSERT INTO operations VALUES (?, ?, ?, 'applied', ?)", (digest([snapshot["run_id"], old_key, "preview"]), snapshot["run_id"], old_key, canonical(old)))
        self.built(snapshot)
        self.validator()
        with patch.object(Reviewer, "security", return_value={"verdict": "pass", "checks": {"synthetic": True}}):
            asyncio.run(self.worker.tick())
        job = self.worker.claim()
        async def exercise():
            with patch("runner.pipeline.socket.socket") as sock, patch("runner.pipeline.httpx.AsyncClient") as client, \
                 patch.object(self.worker.pipeline, "preview_services") as services, patch.object(self.worker.pipeline, "cleanup_preview", return_value=True) as cleanup:
                sock.return_value.__enter__.return_value.getsockname.return_value = ("127.0.0.1", 43111)
                client.return_value.__aenter__.return_value.get = AsyncMock(return_value=httpx.Response(200, json={"status": "ok"}))
                await self.worker.pipeline.release(job, self.worker)
                self.assertEqual(services.call_args.args[1]["data_volume"], old["app"] + "-data")
                cleanup.assert_called_once_with(old)
        asyncio.run(exercise())
        with self.store.transaction() as db:
            states = {r[0] for r in db.execute("SELECT state FROM operations")}
            self.assertEqual(states, {"applied", "superseded"})
            self.assertEqual(json.loads(db.execute("SELECT body FROM previews").fetchone()[0])["data_volume"], old["app"] + "-data")

    def test_lost_preview_result_remains_uncertain_and_blocks_recreation(self):
        async def tick():
            with patch("runner.pipeline.socket.socket") as sock:
                sock.return_value.__enter__.return_value.getsockname.return_value = ("127.0.0.1", 43111)
                await self.worker.tick()
        snapshot = self.built()
        self.validator()
        with patch.object(Reviewer, "security", return_value={"verdict": "pass", "checks": {}}):
            asyncio.run(self.worker.tick())
        with patch.object(self.worker.pipeline, "preview_services", side_effect=ModelUnavailable()), \
             patch.object(self.worker.pipeline, "cleanup_preview", return_value=False):
            asyncio.run(tick())
        waiting = self.store.snapshot(snapshot["run_id"])
        self.assertEqual(waiting["state"], "waiting_resource")
        with self.store.transaction() as db:
            first = dict(db.execute("SELECT * FROM operations").fetchone())
        self.assertEqual(first["state"], "uncertain")
        self.assertEqual(self.post_command(self.command(waiting, "resume")).status_code, 202)
        with patch.object(self.worker.pipeline, "preview_services") as start, \
             patch.object(self.worker.pipeline, "cleanup_preview", return_value=False):
            asyncio.run(tick())
            start.assert_not_called()
        with self.store.transaction() as db:
            operations = [dict(r) for r in db.execute("SELECT * FROM operations")]
        self.assertEqual(len(operations), 2)
        self.assertEqual({r["state"] for r in operations}, {"uncertain"})
        self.assertNotEqual(json.loads(operations[0]["result"])["app"], json.loads(operations[1]["result"])["app"])

    def test_container_cleanup_requires_confirmed_absence(self):
        engine = self.worker.pipeline.engine
        with patch.object(engine, "docker", side_effect=ModelUnavailable()):
            self.assertFalse(engine.cleanup("lifecycle-abc"))
        with patch.object(engine, "docker", side_effect=[ModelUnavailable(), ""]):
            self.assertTrue(engine.cleanup("lifecycle-abc"))
        with patch.object(engine, "docker", side_effect=["", "lifecycle-abc\n"]):
            self.assertFalse(engine.cleanup("lifecycle-abc"))

    def test_cancelled_preview_reconciliation_preserves_unknown_and_data(self):
        snapshot = self.live()
        operation = dict(kind="preview", app="lifecycle-abc", proxy="lifecycle-def", network="lifecycle-aaa", data_volume="lifecycle-abc-data")
        with self.store.transaction() as db:
            db.execute("INSERT INTO operations VALUES ('synthetic', ?, ?, 'applied', ?)", (snapshot["run_id"], digest("synthetic"), canonical(operation)))
        self.post_command(self.command(snapshot, "cancel"))
        with patch.object(self.worker.pipeline, "cleanup_preview", return_value=False) as cleanup:
            asyncio.run(self.worker.tick())
            asyncio.run(self.worker.tick())
            cleanup.assert_called_once_with(operation)
        with self.store.transaction() as db:
            self.assertEqual(db.execute("SELECT state FROM operations").fetchone()[0], "uncertain")
        self.worker.pipeline.recovery_after.clear()
        with patch.object(self.worker.pipeline, "cleanup_preview", return_value=True):
            asyncio.run(self.worker.tick())
        with self.store.transaction() as db:
            row = db.execute("SELECT state,result FROM operations").fetchone()
            self.assertEqual(row[0], "not_applied")
            self.assertEqual(json.loads(row[1])["data_volume"], operation["data_volume"])

    def test_identical_outputs_keep_separate_run_and_spec_bindings(self):
        first = self.built()
        self.post_command(self.command(first, "pause"))
        second = self.built()
        with self.store.transaction() as db:
            rows = db.execute("SELECT id,run_id,spec_version_id,body FROM candidates ORDER BY rowid").fetchall()
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0]["id"], rows[1]["id"])
        self.assertEqual(json.loads(rows[0]["body"])["commit_sha"], json.loads(rows[1]["body"])["commit_sha"])
        self.assertEqual(json.loads(rows[0]["body"])["image_digest"], json.loads(rows[1]["body"])["image_digest"])
        self.assertEqual([(r["run_id"],r["spec_version_id"]) for r in rows],
                         [(first["run_id"],first["spec_version_id"]),(second["run_id"],second["spec_version_id"])])

    def test_not_run_review_is_preserved_and_retried_in_new_cycle(self):
        before = self.built()
        self.validator()
        with patch.object(Reviewer, "security", return_value={"verdict": "not_run", "checks": {}}):
            asyncio.run(self.worker.tick())
        waiting = self.store.snapshot(before["run_id"])
        self.post_command(self.command(waiting, "resume"))
        self.built(self.store.snapshot(before["run_id"]))
        self.validator()
        with patch.object(Reviewer, "security", return_value={"verdict": "pass", "checks": {"synthetic": True}}):
            asyncio.run(self.worker.tick())
        after = self.store.snapshot(before["run_id"])
        self.assertEqual(after["state"], "preview_ready")
        self.assertTrue(all(r["verdict"] == "pass" for r in after["reports"]))
        with self.store.transaction() as db:
            rows = db.execute("SELECT candidate_digest,body FROM reviews WHERE role='security' ORDER BY rowid").fetchall()
            self.assertEqual(len(rows), 2)
            self.assertNotEqual(rows[0]["candidate_digest"], rows[1]["candidate_digest"])
            self.assertEqual([json.loads(row["body"])["verdict"] for row in rows], ["not_run", "pass"])

    def test_command_events_include_id_and_retry_does_not_duplicate(self):
        snapshot = self.planned()
        actions = [("pause", {}), ("resume", {}), ("request_changes", {"scope": "spec", "feedback": "새 기능은 재기획"})]
        for action, payload in actions:
            command = self.command(snapshot, action, payload)
            receipt = self.post_command(command)
            self.assertEqual(receipt.status_code, 202)
            events = self.store.events(snapshot["run_id"], 0)
            self.assertEqual(events[-1]["command_id"], command["command_id"])
            self.assertEqual(self.post_command(command).json(), receipt.json())
            self.assertEqual(self.store.events(snapshot["run_id"], 0), events)
            snapshot = self.store.snapshot(snapshot["run_id"])
        asyncio.run(self.worker.tick())
        snapshot = self.store.snapshot(snapshot["run_id"])
        approval = snapshot["approvals"][-1]
        command = self.command(snapshot, "decide", {"approval_id": approval["id"], "target_digest": approval["target_digest"], "decision": "approve"})
        self.assertEqual(self.post_command(command).status_code, 202)
        self.assertEqual(self.store.events(snapshot["run_id"], 0)[-1]["command_id"], command["command_id"])
