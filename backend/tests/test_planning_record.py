"""Fix A: the model must assess each of the four areas in a fixed structured answer. Fix B: raw model answers are kept in an internal ledger."""
import asyncio
import copy
import json
import sqlite3
import unittest

from jsonschema import Draft202012Validator

from backend.contracts import canonical
from runner.plan_extras import WORK_PLAN_SCHEMA
import test_plan_extras as extras
import test_runtime as fixtures

AREAS = ('infra', 'backend', 'frontend', 'ai_data')


def assessment(**needed):
    return {area: dict(needed=needed.get(area, False), reason=f'{area} 판단 이유') for area in AREAS}


def items(*kinds):
    return [dict(id=f'w{n}', kind=kind, title=f'{kind} 작업', depends_on=[], acceptance_ids=['AC1', 'AC2'], write_scope=[f'{kind}/**'])
            for n, kind in enumerate(kinds)]


def answer(areas, work):
    return dict(areas=areas, work_plan=work, dependencies=dict(pip=[], npm=[]))


class AreaSchema(unittest.TestCase):
    def valid(self, value):
        return Draft202012Validator(WORK_PLAN_SCHEMA).is_valid(value)

    def test_every_area_must_be_judged_with_a_reason(self):
        good = answer(assessment(backend=True, frontend=True), items('backend', 'frontend'))
        self.assertTrue(self.valid(good))
        for area in AREAS:                                   # leaving any one out is impossible under the schema
            broken = copy.deepcopy(good)
            del broken['areas'][area]
            self.assertFalse(self.valid(broken), area)
        for bad in ({'needed': True}, {'needed': 'yes', 'reason': 'x'}, {'needed': False, 'reason': ''}, {'needed': False, 'reason': 'x', 'extra': 1}):
            broken = copy.deepcopy(good)
            broken['areas']['ai_data'] = bad
            self.assertFalse(self.valid(broken), bad)

    def test_the_old_free_form_omission_list_is_no_longer_an_answer(self):
        old = dict(work_plan=items('backend'), omitted_areas=[dict(kind='ai_data', reason='x')], dependencies=dict(pip=[], npm=[]))
        self.assertFalse(self.valid(old))


class AreaPlanning(unittest.TestCase):
    setUp = extras.PlanExtrasChecks.setUp
    command = extras.PlanExtrasChecks.command
    post_command = extras.PlanExtrasChecks.post_command
    start = extras.PlanExtrasChecks.start
    spec = extras.PlanExtrasChecks.spec

    def plan_with(self, areas, work):
        model = extras.Scripted(work_plan=answer(areas, work))
        run_id = self.start(model)
        asyncio.run(self.worker.tick())
        return run_id, model

    def test_areas_judged_not_needed_become_omitted_areas_with_the_models_own_reason(self):
        run_id, _ = self.plan_with(assessment(backend=True, frontend=True), items('backend', 'frontend'))
        snapshot, plan = self.spec(run_id)
        self.assertEqual(snapshot['state'], 'awaiting_plan_approval')
        self.assertEqual(plan['omitted_areas'], [dict(kind='infra', reason='infra 판단 이유'), dict(kind='ai_data', reason='ai_data 판단 이유')])

    def test_an_area_judged_needed_without_a_work_item_is_refused_by_the_existing_check(self):
        run_id, model = self.plan_with(assessment(backend=True, ai_data=True), items('backend'))
        snapshot = self.store.snapshot(run_id)
        self.assertEqual(snapshot['state'], 'needs_input')
        self.assertIn('ai_data', snapshot['reason'])

    def test_an_area_judged_not_needed_that_still_has_a_work_item_is_refused(self):
        run_id, _ = self.plan_with(assessment(backend=True), items('backend', 'frontend'))
        snapshot = self.store.snapshot(run_id)
        self.assertEqual(snapshot['state'], 'needs_input')
        self.assertIn('frontend', snapshot['reason'])

    def test_the_prompt_names_the_fixed_areas_and_carries_no_request_specific_wording(self):
        _, model = self.plan_with(assessment(backend=True, frontend=True), items('backend', 'frontend'))
        call = next(c for c in model.calls if c.get('step') == 'work_plan')
        text = call['instructions']
        for area in AREAS:
            self.assertIn(area, text)
        self.assertIn('needed', text)
        self.assertNotIn('할 일', text)


class ModelOutputLedger(unittest.TestCase):
    setUp = extras.PlanExtrasChecks.setUp
    command = extras.PlanExtrasChecks.command
    post_command = extras.PlanExtrasChecks.post_command
    start = extras.PlanExtrasChecks.start

    def test_every_planning_answer_is_kept_internally_in_order(self):
        run_id = self.start(extras.Scripted())
        asyncio.run(self.worker.tick())
        rows = self.store.model_outputs(run_id)
        steps = [r['step'] for r in rows if r['kind'] == 'output']
        self.assertEqual(steps[:3], ['plan', 'alternatives', 'work_plan'])
        self.assertIn('verification', steps)
        work = next(r for r in rows if r['step'] == 'work_plan')
        self.assertEqual(json.loads(work['content'])['areas']['ai_data']['needed'], False)

    def test_a_rejected_answer_keeps_the_reasons_it_was_rejected_for(self):
        run_id, _ = AreaPlanning.plan_with(self, assessment(backend=True, ai_data=True), items('backend'))
        rejected = [r for r in self.store.model_outputs(run_id) if r['kind'] == 'rejected']
        self.assertTrue(rejected)
        self.assertIn('ai_data', rejected[0]['content'])
        self.assertEqual(rejected[0]['step'], 'work_plan')

    def test_the_ledger_is_not_public_and_cannot_be_rewritten(self):
        run_id = self.start(extras.Scripted())
        asyncio.run(self.worker.tick())
        snapshot = self.store.snapshot(run_id)
        self.assertNotIn('model_outputs', canonical(snapshot))
        for event in self.store.events(run_id, 0):
            self.assertNotIn('areas', canonical(event))
        with self.store.transaction() as db, self.assertRaises(sqlite3.IntegrityError):
            db.execute("UPDATE model_outputs SET content='x'")

    def test_secrets_are_masked_and_long_answers_are_cut(self):
        run_id = self.start(extras.Scripted())
        self.store.record_model_output(dict(run_id=run_id, role='planner', step='plan', kind='output',
                                            content='key=sk-' + 'a' * 30 + ' ' + 'x' * 40000))
        row = self.store.model_outputs(run_id)[-1]
        self.assertNotIn('sk-aaaa', row['content'])
        self.assertIn('[redacted]', row['content'])
        self.assertLessEqual(len(row['content']), 16384)
        self.assertEqual(row['truncated'], 1)


if __name__ == '__main__':
    unittest.main()
