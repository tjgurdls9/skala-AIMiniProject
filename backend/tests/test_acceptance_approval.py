"""F4d: criteria a person must confirm are approved by the user against the exact candidate before a release target can exist.

Every approval below is a test-fixture user command (synthetic), never a real user's approval.
"""
import asyncio
import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from backend.contracts import DomainError, digest, validate
from backend.store import Store
from runner.pipeline import Pipeline
from runner.review import Reviewer
import test_pipeline as pipeline
import test_release as release
import test_runtime as fixtures

PLAN = dict(fixtures.PLAN, acceptance=[dict(id="APP01", title="목록", description="문의 목록이 보인다"),
                                       dict(id="APP02", title="배치", description="화면 배치가 보기 좋다")])
FEEDBACK = "  배치가 너무 \"답답\"해요.\n  — 여백을 늘려 주세요   "
COMMIT, IMAGE = "a" * 40, "sha256:" + "b" * 64


class ManualModel(fixtures.FakeModel):
    """Plans two criteria; the planner marks the second one as something a person must look at."""
    answers_planning_extras = True

    async def generate(self, packet, schema):
        if packet.get("step") == "verification" and packet["acceptance_criterion"]["id"] == "APP02":
            return dict(checks=[], manual_reason="사람이 화면을 본다")
        extras = fixtures.planning_extras(packet)
        return copy.deepcopy(PLAN) if extras is None else extras


class AcceptanceApproval(unittest.TestCase):
    def setUp(self):
        pipeline.PipelineChecks.setUp(self)
        self.worker.model = ManualModel()

    live = fixtures.RuntimeChecks.live
    planned = fixtures.RuntimeChecks.planned
    command = fixtures.RuntimeChecks.command
    post_command = fixtures.RuntimeChecks.post_command
    approved = pipeline.PipelineChecks.approved
    built = pipeline.PipelineChecks.built
    validator = pipeline.PipelineChecks.validator

    def reviewed(self, health="/health"):
        before = self.built(health=health)
        self.validator()
        with patch.object(Reviewer, "security", return_value={"verdict": "pass", "checks": {"synthetic": True}}):
            asyncio.run(self.worker.tick())
        ready = self.store.snapshot(before["run_id"])
        self.assertEqual(ready["state"], "preview_ready")
        return ready

    def publish_preview(self, ready, replies=None):
        """Run the release step with Docker and the app's HTTP answers replaced; returns the recorded health requests."""
        job = self.worker.claim()
        get = AsyncMock(side_effect=replies or [SimpleNamespace(status_code=200)])
        with patch.object(Pipeline, "preview_services"), patch.object(Pipeline, "retire_preview"), patch("httpx.AsyncClient.get", new=get):
            asyncio.run(self.worker.pipeline.release(job, self.worker))
        self.assertEqual(get.await_count, len(replies or [0]))
        return [call.args[0] for call in get.await_args_list], self.store.snapshot(ready["run_id"])

    def previewed(self):
        return self.publish_preview(self.reviewed())[1]

    def package(self, snapshot):
        with self.store.transaction() as db:
            return json.loads(db.execute("SELECT package FROM specs WHERE id=?", (snapshot["spec_version_id"],)).fetchone()[0])

    @staticmethod
    def acceptance_approvals(snapshot):
        return [a for a in snapshot["approvals"] if a["target"]["gate"] == "acceptance"]

    def decide(self, snapshot, decision, approval=None, **payload):
        approval = approval or self.acceptance_approvals(snapshot)[-1]
        return self.post_command(self.command(snapshot, "decide", dict(
            approval_id=approval["id"], target_digest=payload.pop("target_digest", approval["target_digest"]), decision=decision, **payload)))

    # -- validator verdict ------------------------------------------------------------------------------
    def test_the_validator_passes_while_the_human_criterion_stays_not_run(self):
        ready = self.reviewed()
        report = next(r for r in ready["reports"] if r["role"] == "validator")
        self.assertEqual(report["verdict"], "pass")
        self.assertEqual(self.store.read_artifact(report["artifact_id"])["manual_pending"], ["APP02"])
        status = {i["id"]: i["status"] for i in self.store.acceptance_status(ready["run_id"])["items"]}
        self.assertEqual(status, {"APP01": "met", "APP02": "not_run"})

    # -- creating the approval --------------------------------------------------------------------------
    def test_publishing_the_preview_requests_one_approval_bound_to_the_exact_candidate(self):
        ready = self.reviewed()
        self.assertEqual(self.acceptance_approvals(ready), [])          # nothing to confirm until there is a preview to look at
        snapshot = self.publish_preview(ready)[1]
        [approval] = self.acceptance_approvals(snapshot)
        validator = next(r for r in snapshot["reports"] if r["role"] == "validator")
        expected = dict(gate="acceptance", spec_version_id=snapshot["spec_version_id"], plan_digest=digest(self.package(snapshot)),
                        commit_sha=COMMIT, image_digest=IMAGE, ac_ids=["APP02"],
                        validator_report_id=validator["id"], validator_report_digest=validator["content_digest"])
        validate("AcceptanceTarget", approval["target"])
        self.assertEqual(approval["target"], expected)
        self.assertEqual((approval["state"], approval["target_digest"], snapshot["state"]), ("pending", digest(expected), "preview_ready"))
        validate("Snapshot", snapshot)

    def test_running_the_release_step_again_does_not_ask_twice(self):
        snapshot = self.previewed()
        self.assertEqual(self.post_command(self.command(snapshot, "pause")).status_code, 202)
        paused = self.store.snapshot(snapshot["run_id"])
        self.assertEqual(self.post_command(self.command(paused, "resume")).status_code, 202)
        again = self.publish_preview(snapshot)[1]
        self.assertEqual([a["state"] for a in self.acceptance_approvals(again)], ["pending"])

    def test_no_human_criterion_means_no_acceptance_approval(self):
        self.worker.model = fixtures.FakeModel()
        snapshot = self.previewed()
        self.assertEqual((snapshot["state"], self.acceptance_approvals(snapshot)), ("preview_ready", []))

    # -- the declared health path -----------------------------------------------------------------------
    def test_the_preview_is_checked_on_the_health_path_the_app_declared(self):
        ready = self.reviewed(health="/ready")
        urls, snapshot = self.publish_preview(ready, [SimpleNamespace(status_code=503), SimpleNamespace(status_code=200)])
        self.assertEqual([u.rsplit("/", 1)[1] for u in urls], ["ready", "ready"])
        self.assertTrue(any(a["kind"] == "preview" for a in snapshot["artifacts"]))

    # -- deciding ---------------------------------------------------------------------------------------
    def test_approving_binds_the_user_decision_and_leaves_the_validator_verdict_alone(self):
        snapshot = self.previewed()
        self.assertEqual(self.decide(snapshot, "approve").status_code, 202)
        after = self.store.snapshot(snapshot["run_id"])
        [approval] = self.acceptance_approvals(after)
        self.assertEqual((approval["state"], approval["decided_by"], after["state"]), ("approved", "local-operator", "preview_ready"))
        self.assertEqual(after["reports"], snapshot["reports"])
        status = {i["id"]: i["status"] for i in self.store.acceptance_status(after["run_id"])["items"]}
        self.assertEqual(status["APP02"], "not_run")

    def test_rejecting_keeps_the_users_words_verbatim_and_asks_for_input(self):
        snapshot = self.previewed()
        self.assertEqual(self.decide(snapshot, "reject", feedback=FEEDBACK).status_code, 202)
        after = self.store.snapshot(snapshot["run_id"])
        [approval] = self.acceptance_approvals(after)
        self.assertEqual((approval["state"], approval["feedback"], after["state"]), ("rejected", FEEDBACK, "needs_input"))
        with self.store.transaction() as db:
            saved = [r[0] for r in db.execute("SELECT content FROM requests WHERE run_id=?", (after["run_id"],))]
        self.assertEqual(saved, [FEEDBACK])

    def test_a_decision_needs_the_current_target_and_the_preview_state(self):
        snapshot = self.previewed()
        wrong = self.decide(snapshot, "approve", target_digest="sha256:" + "0" * 64)
        self.assertEqual((wrong.status_code, wrong.json()["error"]["code"]), (409, "STALE_APPROVAL"))
        self.assertEqual(self.post_command(self.command(snapshot, "pause")).status_code, 202)
        paused = self.store.snapshot(snapshot["run_id"])
        early = self.decide(paused, "approve", approval=self.acceptance_approvals(paused)[0])
        self.assertEqual((early.status_code, early.json()["error"]["code"]), (409, "INVALID_STATE"))
        self.assertEqual(self.acceptance_approvals(self.store.snapshot(snapshot["run_id"]))[0]["state"], "pending")

    def test_an_approval_for_a_candidate_that_is_no_longer_current_is_stale(self):
        snapshot = self.previewed()
        with self.store.transaction() as db:
            changed = self.store.load(db, snapshot["run_id"])
            changed["reports"][0]["commit_sha"] = "c" * 40
            db.execute("UPDATE runs SET snapshot=? WHERE id=?", (json.dumps(changed), snapshot["run_id"]))
        response = self.decide(self.store.snapshot(snapshot["run_id"]), "approve")
        self.assertEqual((response.status_code, response.json()["error"]["code"]), (409, "STALE_APPROVAL"))

    # -- invalidation -----------------------------------------------------------------------------------
    def test_a_change_request_invalidates_an_approved_confirmation(self):
        snapshot = self.previewed()
        self.decide(snapshot, "approve")
        approved = self.store.snapshot(snapshot["run_id"])
        self.assertEqual(self.post_command(self.command(approved, "request_changes", dict(scope="implementation", feedback="여백"))).status_code, 202)
        self.assertEqual([a["state"] for a in self.acceptance_approvals(self.store.snapshot(snapshot["run_id"]))], ["invalidated"])

    def test_a_rebuild_invalidates_an_approved_confirmation(self):
        snapshot = self.previewed()
        self.decide(snapshot, "approve")
        with self.store.transaction() as db:       # a user-visible path to rebuilding an approved candidate: the run is stopped and resumed into building
            stopped = self.store.load(db, snapshot["run_id"])
            stopped["state"] = "needs_input"
            db.execute("UPDATE runs SET snapshot=?, resume_state='building' WHERE id=?", (json.dumps(stopped), snapshot["run_id"]))
        resumed = self.store.snapshot(snapshot["run_id"])
        self.assertEqual(self.post_command(self.command(resumed, "resume")).status_code, 202)
        after = self.store.snapshot(snapshot["run_id"])
        self.assertEqual((after["state"], [a["state"] for a in self.acceptance_approvals(after)]), ("building", ["invalidated"]))

    def test_a_newly_frozen_candidate_invalidates_a_leftover_confirmation(self):
        snapshot = self.previewed()
        self.decide(snapshot, "approve")
        with self.store.transaction() as db:
            stopped = self.store.load(db, snapshot["run_id"])
            stopped["state"] = "needs_input"
            db.execute("UPDATE runs SET snapshot=?, resume_state='building' WHERE id=?", (json.dumps(stopped), snapshot["run_id"]))
        self.post_command(self.command(self.store.snapshot(snapshot["run_id"]), "resume"))
        with self.store.transaction() as db:       # the resume itself already invalidated it; put it back to prove the build step does too
            leftover = self.store.load(db, snapshot["run_id"])
            [approval] = self.acceptance_approvals(leftover)
            approval["state"] = "approved"
            db.execute("UPDATE runs SET snapshot=? WHERE id=?", (json.dumps(leftover), snapshot["run_id"]))
        after = self.built(self.store.snapshot(snapshot["run_id"]))
        self.assertEqual([a["state"] for a in self.acceptance_approvals(after)], ["invalidated"])

    def test_invalidation_touches_only_pending_and_approved_confirmations(self):
        snapshot = dict(approvals=[dict(id=str(i), state=state, target=dict(gate=gate)) for i, (gate, state) in enumerate(
            [("acceptance", "pending"), ("acceptance", "approved"), ("acceptance", "rejected"), ("plan", "approved"), ("release", "pending")])])
        self.assertTrue(Store.invalidate_acceptance(snapshot))
        self.assertEqual([a["state"] for a in snapshot["approvals"]], ["invalidated", "invalidated", "rejected", "approved", "pending"])
        self.assertFalse(Store.invalidate_acceptance(snapshot))


class ReleaseBinding(unittest.TestCase):
    """A candidate with human-confirmed criteria cannot get a release target, or run one, without the matching approval."""
    MANUAL = [dict(ac_id="APP01", reason="사람이 화면을 본다")]
    PREPARE = False
    setUp = release.ReleaseChecks.setUp
    prepare = release.ReleaseChecks.prepare
    approve_fixture = release.ReleaseChecks.approve_fixture

    def confirm(self, state="approved", **other):
        """A user confirmation of this candidate; `other` overrides target fields (an approval for something else)."""
        with self.store.transaction() as db:
            snapshot = self.store.load(db, self.snapshot["run_id"])
            target = dict(Store.acceptance_target(snapshot, self.package, self.candidate["commit_sha"], self.candidate["image_digest"]), **other)
            approval = dict(id=release.uid(), state=state, target=target, target_digest=digest(target))
            snapshot["approvals"].append(approval)
            self.store.save(db, snapshot, "warning", "synthetic fixture user confirmation")
        return approval

    def test_no_release_target_without_an_approved_confirmation_of_this_candidate(self):
        for state in ("pending", "rejected", "invalidated"):
            self.confirm(state)
        self.confirm("approved", commit_sha="d" * 40)
        self.confirm("approved", ac_ids=["APP99"])
        with self.assertRaises(DomainError) as refused:
            self.prepare()
        self.assertEqual(refused.exception.code, "STALE_APPROVAL")
        self.confirm()
        self.assertIn("acceptance_approval_id", self.prepare()["target"])

    def test_the_target_names_the_confirmation_it_depends_on(self):
        approval = self.confirm()
        manifest = self.prepare()
        validate("ReleaseTarget", manifest["target"])
        self.assertEqual(manifest["target"]["acceptance_approval_id"], approval["id"])

    def test_no_mutation_runs_after_the_confirmation_is_invalidated(self):
        approval = self.confirm()
        self.manifest = self.prepare()
        self.approve_fixture()
        with self.store.transaction() as db:
            snapshot = self.store.load(db, self.snapshot["run_id"])
            next(a for a in snapshot["approvals"] if a["id"] == approval["id"])["state"] = "invalidated"
            self.store.save(db, snapshot, "warning", "synthetic fixture invalidation")
        with patch.object(self.operations.git, "push") as push:
            with self.assertRaises(DomainError):
                self.operations.apply(self.snapshot["run_id"], self.manifest, "push")
        push.assert_not_called()


if __name__ == "__main__":
    unittest.main()
