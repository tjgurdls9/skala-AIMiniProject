"""C4: one small generic request goes through every stage with a fake model, up to the point where a release target can be prepared.

Every user decision below is a test-fixture command (synthetic); none counts as a real user's approval, and the review
containers, preview containers and Docker builds are replaced, so this proves the service's orchestration, not model quality.
"""
import asyncio
import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from backend.contracts import DomainError, digest
from backend.store import Store
from runner.check_runner import CheckOutcome
from runner.pipeline import Pipeline
from runner.release import ReleaseOperations
from runner.review import Reviewer
import test_model_build as build
import test_plan_extras as extras


def verification(packet):
    """AC1 gets a mechanical check; AC2 is something only a person can judge."""
    ac = packet['acceptance_criterion']['id']
    if ac == 'AC2':
        return dict(checks=[], manual_reason='사람이 화면 배치를 본다')
    return dict(checks=[dict(extras.http_check(ac), ac_ids=[ac])], manual_reason=None)


class FullFlow(unittest.TestCase):
    setUp = build.ModelBuildChecks.setUp
    command = build.ModelBuildChecks.command
    post_command = build.ModelBuildChecks.post_command
    approved_run = build.ModelBuildChecks.approved_run
    drain = build.ModelBuildChecks.drain

    def decide(self, run_id, gate, decision):
        snapshot = self.store.snapshot(run_id)
        approval = next(a for a in snapshot['approvals'] if a['target']['gate'] == gate and a['state'] == 'pending')
        response = self.post_command(self.command(snapshot, 'decide', dict(approval_id=approval['id'], target_digest=approval['target_digest'], decision=decision)))
        self.assertEqual(response.status_code, 202, response.text)

    def review_and_preview(self, run_id):
        outcomes = ([CheckOutcome('AC1-1', 'passed', '', {})], dict(healthy=True))
        with patch.object(Reviewer, 'model_validation', return_value=outcomes), patch.object(Reviewer, 'security', return_value=dict(verdict='pass', checks={'synthetic': True})):
            asyncio.run(self.worker.tick())
            asyncio.run(self.worker.tick())
        self.assertEqual(self.store.snapshot(run_id)['state'], 'preview_ready')
        job = self.worker.claim()
        self.assertEqual(job['role'], 'release')
        with patch.object(Pipeline, 'preview_services'), patch.object(Pipeline, 'retire_preview'), \
             patch('httpx.AsyncClient.get', new=AsyncMock(return_value=SimpleNamespace(status_code=200))):
            asyncio.run(self.worker.pipeline.release(job, self.worker))
        return self.store.snapshot(run_id)

    def test_a_request_passes_planning_building_review_preview_and_the_human_confirmation(self):
        run_id = self.approved_run(build.BuildScripted(verification=verification))
        planned = self.store.snapshot(run_id)
        with self.store.transaction() as db:
            plan = json.loads(db.execute('SELECT package FROM specs WHERE id=?', (planned['spec_version_id'],)).fetchone()[0])
        self.assertEqual([c['id'] for c in plan['verification']], ['AC1-1'])
        self.assertEqual([m['ac_id'] for m in plan['manual_acceptance']], ['AC2'])
        self.assertTrue(plan['alternatives'] and plan['work_plan'] and plan['selected_alternative_id'])

        frozen = self.drain(run_id)                                  # the model built every task; the server froze one candidate
        self.assertEqual(frozen['state'], 'reviewing')
        self.assertEqual(self.store.interventions(run_id), [])       # every workspace change is in the tool ledger
        self.assertTrue(self.store.tool_calls(run_id))

        ready = self.review_and_preview(run_id)
        self.assertEqual({r['role']: r['verdict'] for r in ready['reports']}, {'validator': 'pass', 'security': 'pass'})
        status = {i['id']: i['status'] for i in self.store.acceptance_status(run_id)['items']}
        self.assertEqual(status, {'AC1': 'met', 'AC2': 'not_run'})
        self.assertEqual([(a['target']['gate'], a['state']) for a in ready['approvals']], [('plan', 'approved'), ('acceptance', 'pending')])

        self.decide(run_id, 'acceptance', 'approve')
        final = self.store.snapshot(run_id)
        self.assertEqual([(a['target']['gate'], a['state']) for a in final['approvals']], [('plan', 'approved'), ('acceptance', 'approved')])
        self.assertEqual(final['state'], 'preview_ready')
        self.assertEqual({i['id']: i['status'] for i in self.store.acceptance_status(run_id)['items']}['AC2'], 'not_run')   # a person's yes is not a check result

        # every release precondition is on record ...
        candidate = self.store.code_diffs(run_id)[-1]            # the last task's commit is the frozen candidate
        self.assertIsNotNone(Store.acceptance_approval(final, plan, candidate['commit'], 'sha256:' + 'b' * 64))
        # ... but no repository or environment was ever chosen for this plan, so no release target exists (a user/operator decision, S10)
        operations = ReleaseOperations(self.store, current=lambda db: True)
        repository = dict(url='https://github.com/test/generated.git', branch='generated/fixture', auto_deploy=False)
        environment = dict(id='local', label='local', provider='docker_local', exposure='local', port=49101, free_verified=True, free_evidence='synthetic')
        with self.assertRaises(DomainError) as refused:
            operations.prepare(run_id, repository, environment, 'registry.example/test/app@sha256:' + 'c' * 64)
        self.assertEqual(refused.exception.code, 'STALE_APPROVAL')
        self.assertEqual(self.store.release_view(run_id)['state'], 'unconfigured')


if __name__ == '__main__':
    unittest.main()
