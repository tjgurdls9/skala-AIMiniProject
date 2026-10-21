"""CT40 regression: explicit corrections retire mutable requirements, never original records."""
import asyncio
import copy
import json
import unittest

from backend.contracts import digest
from runner.context import fragments
import test_runtime as fixtures

OLD = dict(goal='red 문의', features=['문의 목록', '삭제 기능'], non_goals=['모바일'], constraints=['red'],
           assumptions=['합성 데이터'], changes=[], acceptance=[dict(id='APP01', title='목록', description='red 항목 목록')])
NEW = dict(goal='blue 문의', features=['문의 목록'], non_goals=[], constraints=['blue'], assumptions=['합성 데이터'],
           changes=['명시 정정'], acceptance=[dict(id='APP01', title='목록', description='blue 항목 목록')])
CORRECTION = '앞의 red 목표와 red 제약은 blue로 대체하고 삭제 기능과 모바일 비범위는 철회한다. APP01 설명은 blue 항목 목록으로 바꾼다.'
RETIRED = [('goal', OLD['goal']), ('features', '삭제 기능'), ('constraints', 'red'), ('non_goals', '모바일'), ('acceptance', OLD['acceptance'][0])]


class Correcting(fixtures.FakeModel):
    async def generate(self, packet, schema):
        if CORRECTION not in packet['original_or_correction']['text']:
            return copy.deepcopy(OLD)
        return dict(copy.deepcopy(NEW), revisions=[dict(field=field, previous_digest=digest(value), quote=CORRECTION) for field, value in RETIRED])


class CorrectionChecks(unittest.TestCase):
    setUp = fixtures.RuntimeChecks.setUp
    live = fixtures.RuntimeChecks.live
    planned = fixtures.RuntimeChecks.planned
    command = fixtures.RuntimeChecks.command
    post_command = fixtures.RuntimeChecks.post_command

    def assert_current(self, snapshot):
        self.assertEqual(snapshot['state'], 'awaiting_plan_approval')
        artifact = next(a for a in reversed(snapshot['artifacts']) if a['kind'] == 'spec')
        plan = self.store.read_artifact(artifact['id'])
        for key in ('goal', 'features', 'non_goals', 'constraints', 'acceptance'):
            self.assertEqual(plan[key], NEW[key])
        self.assertEqual(plan['free_policy'], 'Inference: local Ollama Qwen/DeepSeek only; no paid fallback or external model API. External data: verified free terms, explicit consent, fixed isolated access, no paid overage.')
        with self.store.transaction() as db:
            checkpoints = [json.loads(r[0]) for r in db.execute('SELECT body FROM context_steps ORDER BY rowid')]
        self.assertEqual(len(checkpoints[-1]['revisions']), 5)
        self.assertEqual(checkpoints[-1]['plan']['constraints'], ['blue'])
        return plan

    def test_later_fragment_replaces_and_deletes_in_same_request(self):
        self.worker.model = Correcting()
        self.worker.heartbeat()
        prefix = 'red 문의, 삭제 기능, 모바일 비범위, red 항목 목록.\n'
        raw = prefix + ' ' * (2400 - len(prefix.encode())) + CORRECTION
        project = self.store.project(dict(title='synthetic correction', request=raw))
        run = self.store.create_run(project['project_id'], dict(mode='live'))
        asyncio.run(self.worker.tick())
        self.assert_current(self.store.snapshot(run['run_id']))
        with self.store.transaction() as db:
            request = dict(db.execute('SELECT * FROM requests').fetchone())
        self.assertEqual(request['content'], raw)
        self.assertEqual(''.join(p['text'] for p in fragments([request])), raw)

    def test_followup_correction_invalidates_old_approval_and_changes_execution_input(self):
        class Initial(fixtures.FakeModel):
            async def generate(self, packet, schema):
                return copy.deepcopy(OLD)
        self.worker.model = Initial()
        before = self.planned()
        old_approval = before['approvals'][-1]
        self.post_command(self.command(before, 'request_changes', dict(scope='spec', feedback=CORRECTION)))
        self.worker.model = Correcting()
        asyncio.run(self.worker.tick())
        current = self.store.snapshot(before['run_id'])
        self.assert_current(current)
        self.assertEqual(current['approvals'][0]['state'], 'invalidated')
        self.assertNotEqual(current['spec_version_id'], before['spec_version_id'])
        stale = self.post_command(self.command(current, 'decide', dict(approval_id=old_approval['id'], target_digest=old_approval['target_digest'], decision='approve')))
        self.assertEqual(stale.status_code, 409)
        with self.store.transaction() as db:
            requests = [r[0] for r in db.execute('SELECT content FROM requests ORDER BY rowid')]
        self.assertEqual(requests[-1], CORRECTION)
        # Synthetic fixture decision checks propagation; it is not real user HITL evidence.
        approval = current['approvals'][-1]
        response = self.post_command(self.command(current, 'decide', dict(approval_id=approval['id'], target_digest=approval['target_digest'], decision='approve')))
        self.assertEqual(response.status_code, 202)
        job = self.worker.claim()
        self.assertEqual(job['packet']['latest_spec']['constraints'], ['blue'])
        self.assertEqual(job['packet']['latest_spec']['acceptance'], NEW['acceptance'])

    def test_unexplained_model_omission_does_not_create_current_plan(self):
        class Forgetting(Correcting):
            async def generate(self, packet, schema):
                value = await super().generate(packet, schema)
                value.pop('revisions', None)
                return value
        self.worker.model = Forgetting()
        self.worker.heartbeat()
        raw = 'x' * 2400 + CORRECTION
        project = self.store.project(dict(title='synthetic omission', request=raw))
        run = self.store.create_run(project['project_id'], dict(mode='live'))
        asyncio.run(self.worker.tick())
        result = self.store.snapshot(run['run_id'])
        self.assertEqual(result['state'], 'needs_input')
        self.assertFalse(result['approvals'])
