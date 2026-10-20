"""Synthetic orchestration checks; mocked tools never represent product review PASS."""
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from backend.contracts import DomainError, canonical, digest
from runner.access import RoleScope, issue_grant
from runner.review import Reviewer, scan_covered
from runner.worker import Worker, failure_reason
from runner.model import ModelUnavailable, sampling_schema
import test_runtime as fixtures


class PipelineChecks(unittest.TestCase):
    setUp = fixtures.RuntimeChecks.setUp
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

    def built(self, snapshot=None):
        snapshot = snapshot or self.approved()
        job = self.worker.claim()
        workspace = self.worker.pipeline.engine.workspace(job["run_id"], snapshot["spec_version_id"])
        candidate = dict(commit_sha="a" * 40, image_digest="sha256:" + "b" * 64, manifest={}, path=str(workspace))
        async def output(packet, schema):
            return dict(summary="synthetic unchanged template", files=[])
        with patch.object(self.worker.pipeline.engine, "runtime", return_value=candidate["image_digest"]), \
             patch.object(self.worker.pipeline.engine, "freeze", return_value=candidate), \
             patch.object(self.worker.model, "generate", side_effect=output):
            asyncio.run(self.worker.pipeline.build(job, self.worker))
        return self.store.snapshot(snapshot["run_id"])

    def validator(self):
        async def output(packet, schema):
            self.assertNotIn("reports", packet)
            self.assertNotIn("security_report", packet)
            return dict(summary="synthetic", acceptance=[dict(id="APP01", status="met", evidence=["list"])])
        with patch.object(Reviewer, "validation", return_value={"checks": {"list": True}}), \
             patch.object(self.worker.model, "generate", side_effect=output):
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

    def test_review_same_candidate_gate_and_style_write_boundary(self):
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
        response = self.post_command(self.command(ready, "request_changes", {"scope": "implementation", "feedback": "배경색과 여백을 바꿔 주세요"}))
        self.assertEqual(response.status_code, 202, response.text)
        changed = self.store.snapshot(ready["run_id"])
        self.assertEqual(changed["state"], "building")
        self.assertEqual(changed["spec_version_id"], ready["spec_version_id"])
        self.assertFalse(changed["reports"])
        builder = self.worker.claim()
        workspace = self.worker.pipeline.engine.workspace(builder["run_id"], changed["spec_version_id"])
        scope = RoleScope(self.store, issue_grant(self.store, builder, workspace))
        with self.assertRaises(DomainError):
            scope.patch("app_backend/main.py", "changed", digest((workspace / "app_backend/main.py").read_text()))
        old = scope.read("app_frontend/style.css")
        scope.patch(old["path"], old["content"] + "\n/* synthetic */", old["content_digest"])
        feature = self.post_command(self.command(changed, "request_changes", {"scope": "implementation", "feedback": "색 변경과 결제 기능 추가"}))
        self.assertEqual(feature.status_code, 202)
        replanned = self.store.snapshot(changed["run_id"])
        self.assertEqual(replanned["state"], "planning")
        self.assertIsNone(replanned["spec_version_id"])
        self.assertTrue(all(a["state"] == "invalidated" for a in replanned["approvals"]))

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

    def test_sampling_keeps_server_schema_and_path_enum(self):
        from runner.sandbox import PATCH_SCHEMA
        sampled = sampling_schema(PATCH_SCHEMA)
        self.assertNotIn("maxLength", canonical(sampled))
        self.assertEqual(PATCH_SCHEMA["properties"]["files"]["items"]["properties"]["content"]["maxLength"], 65536)
        self.assertEqual(sampled["properties"]["files"]["items"]["properties"]["path"], PATCH_SCHEMA["properties"]["files"]["items"]["properties"]["path"])
        self.assertEqual(failure_reason(ExceptionGroup("stdio", [ModelUnavailable()]))[0], "waiting_resource")

    def test_stale_review_cannot_publish(self):
        before = self.built()
        job = self.worker.claim()
        self.post_command(self.command(before, "pause"))
        async def output(packet, schema):
            return dict(summary="late", acceptance=[])
        with patch.object(Reviewer, "validation", return_value={"checks": {}}), patch.object(self.worker, "infer", side_effect=output):
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
                 patch.object(self.worker.pipeline, "preview_services") as services, patch.object(self.worker.pipeline, "cleanup_preview") as cleanup:
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
