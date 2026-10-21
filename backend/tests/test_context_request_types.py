"""F0: planning-context behaviour per generic request type, with scripted fake models only.

No model, worker process or Ollama is started. Requests are neutral placeholders, never a real task.
"""
import asyncio
import copy
import json
import unittest

from backend.contracts import SCHEMAS, canonical, digest
from runner.context import BUDGET, FRAGMENT_BYTES, PlanningContext, fragments
from runner.model import ModelUnavailable
import test_context_corrections as corrections
import test_runtime as fixtures

PLAN_SCHEMA = SCHEMAS['http.v1.schema.json']['$defs']['PlanDraft']
PLANNER_KEYS = {'role', 'mandatory_policy', 'approved_spec', 'prior_draft', 'unresolved_failures', 'original_or_correction',
                'accumulated_plan', 'source_digest', 'fragment_index', 'total_fragments', 'retrieved_documents',
                'template_contract', 'instructions', 'prior_values'}


def plan_with(constraint):
    return dict(copy.deepcopy(fixtures.PLAN), constraints=[constraint])


class ChainModel(fixtures.FakeModel):
    """Each fragment reads 'constraint:<name>' or 'replace:<old>-><new>' and updates the current plan."""
    def __init__(self):
        self.calls = []

    async def generate(self, packet, schema):
        self.calls.append(packet)
        text = packet['original_or_correction']['text']
        if 'replace:' not in text:
            if 'constraint:' in text:
                return plan_with(text.split('constraint:')[1].split()[0])
            # A fragment without a stated requirement keeps the plan read so far.
            return copy.deepcopy(packet['accumulated_plan']) if packet['accumulated_plan'] else plan_with('initial')
        old, new = text.split('replace:')[1].split()[0].split('->')
        revision = dict(field='constraints', previous_digest=digest(old), quote=f'replace:{old}->{new}')
        return dict(plan_with(new), revisions=[revision])


class RequestTypeChecks(unittest.TestCase):
    setUp = fixtures.RuntimeChecks.setUp
    live = fixtures.RuntimeChecks.live
    planned = fixtures.RuntimeChecks.planned
    command = fixtures.RuntimeChecks.command
    post_command = fixtures.RuntimeChecks.post_command

    def start(self, model, request):
        self.worker.model = model
        self.worker.heartbeat()
        project = self.store.project(dict(title='generic request', request=request))
        return self.store.create_run(project['project_id'], dict(mode='live'))['run_id']

    def spec_of(self, snapshot):
        artifact = next(a for a in reversed(snapshot['artifacts']) if a['kind'] == 'spec')
        return self.store.read_artifact(artifact['id'])

    def test_short_request_completes_in_one_model_call(self):
        model = ChainModel()
        run_id = self.start(model, 'constraint:alpha')
        asyncio.run(self.worker.tick())
        snapshot = self.store.snapshot(run_id)
        self.assertEqual(snapshot['state'], 'awaiting_plan_approval')
        self.assertEqual(len(model.calls), 1)
        self.assertEqual(model.calls[0]['total_fragments'], 1)
        self.assertEqual(self.spec_of(snapshot)['constraints'], ['alpha'])

    def test_long_request_is_read_in_full_across_fragments(self):
        raw = 'constraint:alpha ' + 'x' * (FRAGMENT_BYTES * 2 + 100)
        model = ChainModel()
        run_id = self.start(model, raw)
        asyncio.run(self.worker.tick())
        snapshot = self.store.snapshot(run_id)
        self.assertEqual(snapshot['state'], 'awaiting_plan_approval')
        self.assertEqual(len(model.calls), 3)
        self.assertEqual(''.join(c['original_or_correction']['text'] for c in model.calls), raw)
        self.assertTrue(all(len(canonical(c).encode()) <= BUDGET for c in model.calls))
        context = next(a for a in snapshot['artifacts'] if a['kind'] == 'context')
        evidence = self.store.read_artifact(context['id'])
        self.assertEqual((evidence['status'], evidence['completed_fragments'], evidence['total_fragments']), ('ready', 3, 3))

    def test_chain_of_corrections_never_revives_retired_requirements(self):
        model = ChainModel()
        run_id = self.start(model, 'constraint:alpha')
        asyncio.run(self.worker.tick())
        for old, new in (('alpha', 'beta'), ('beta', 'gamma')):
            current = self.store.snapshot(run_id)
            self.post_command(self.command(current, 'request_changes', dict(scope='spec', feedback=f'replace:{old}->{new}')))
            asyncio.run(self.worker.tick())
        snapshot = self.store.snapshot(run_id)
        self.assertEqual(snapshot['state'], 'awaiting_plan_approval')
        plan = self.spec_of(snapshot)
        self.assertEqual(plan['constraints'], ['gamma'])
        self.assertNotIn('alpha', canonical({k: plan[k] for k in ('goal', 'features', 'constraints', 'acceptance')}))
        self.assertEqual([a['state'] for a in snapshot['approvals']][:-1], ['invalidated', 'invalidated'])
        with self.store.transaction() as db:
            requests = [r[0] for r in db.execute('SELECT content FROM requests ORDER BY rowid')]
        self.assertEqual(requests, ['constraint:alpha', 'replace:alpha->beta', 'replace:beta->gamma'])

    def test_replan_carries_prior_draft_but_never_as_approved_scope(self):
        model = ChainModel()
        run_id = self.start(model, 'constraint:alpha')
        asyncio.run(self.worker.tick())
        first = self.store.snapshot(run_id)
        self.post_command(self.command(first, 'request_changes', dict(scope='spec', feedback='replace:alpha->beta')))
        model.calls.clear()
        asyncio.run(self.worker.tick())
        self.assertTrue(model.calls)
        self.assertTrue(all(c['approved_spec'] is None for c in model.calls))
        self.assertTrue(all(c['prior_draft']['constraints'] == ['alpha'] for c in model.calls))

    def test_replan_after_approval_keeps_old_scope_out_of_approved_slot(self):
        model = ChainModel()
        run_id = self.start(model, 'constraint:alpha')
        asyncio.run(self.worker.tick())
        planned = self.store.snapshot(run_id)
        approval = planned['approvals'][-1]
        self.post_command(self.command(planned, 'decide', dict(approval_id=approval['id'], target_digest=approval['target_digest'], decision='approve')))
        job = self.worker.claim()
        self.assertEqual(job['role'], 'builder')
        self.assertEqual(job['packet']['latest_spec']['constraints'], ['alpha'])
        self.assertIsNone(job['packet']['prior_draft'])

    def test_planner_input_keys_are_pinned_and_contain_no_review_results(self):
        model = ChainModel()
        self.start(model, 'constraint:alpha')
        asyncio.run(self.worker.tick())
        for call in model.calls:
            self.assertEqual(set(call), PLANNER_KEYS)
            self.assertFalse([k for k in call if 'report' in k or 'review' in k or 'security' in k])

    def test_interrupted_planning_reuses_saved_fragments_and_never_regenerates_them(self):
        raw = 'constraint:alpha ' + 'x' * (FRAGMENT_BYTES + 100)

        class Flaky(ChainModel):
            fail = True
            async def generate(self, packet, schema):
                if self.fail and packet['fragment_index'] == 1:
                    raise ModelUnavailable('synthetic outage')
                return await super().generate(packet, schema)
        model = Flaky()
        self.start(model, raw)
        job = self.worker.claim()
        with self.assertRaises(ModelUnavailable):
            asyncio.run(PlanningContext(self.store).plan(job, self.worker, PLAN_SCHEMA))
        self.assertEqual([c['fragment_index'] for c in model.calls], [0])
        model.fail = False
        asyncio.run(PlanningContext(self.store).plan(job, self.worker, PLAN_SCHEMA))
        self.assertEqual([c['fragment_index'] for c in model.calls], [0, 1])

    def test_fragments_cover_every_byte_exactly_once_for_multibyte_text(self):
        raw = '요구 ' * 1500
        parts = fragments([dict(id='r1', content=raw)])
        self.assertEqual(''.join(p['text'] for p in parts), raw)
        self.assertTrue(all(p['length'] <= FRAGMENT_BYTES for p in parts))
        self.assertEqual([p['offset'] for p in parts], sorted(p['offset'] for p in parts))


if __name__ == '__main__':
    unittest.main()
