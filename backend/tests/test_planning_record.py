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


class VerificationRetry(unittest.TestCase):
    setUp = extras.PlanExtrasChecks.setUp
    command = extras.PlanExtrasChecks.command
    post_command = extras.PlanExtrasChecks.post_command
    start = extras.PlanExtrasChecks.start
    spec = extras.PlanExtrasChecks.spec

    def test_the_model_is_told_which_of_its_checks_is_wrong_and_can_fix_it(self):
        seen = []

        def verification(packet):
            ac = packet['acceptance_criterion']['id']
            seen.append(packet.get('previous_errors'))
            path = '/app/server.py' if len(seen) == 1 else 'server.py'
            return dict(checks=[dict(extras.http_check(ac), ac_ids=[ac], id='OWN-1'),
                                dict(id='OWN-2', ac_ids=[ac], kind='file', path=path, expect=dict(exists=True))], manual_reason=None)
        run_id = self.start(extras.Scripted(verification=verification))
        asyncio.run(self.worker.tick())
        self.assertEqual(self.store.snapshot(run_id)['state'], 'awaiting_plan_approval')
        self.assertIsNone(seen[0])
        self.assertIn('OWN-2', ' '.join(seen[1]))
        self.assertNotIn('c2', ' '.join(seen[1]))


class AlternatingMistakes(unittest.TestCase):
    """Live run b7630a: the model alternated between two wrong answers, so "the same error twice in a row" never happened."""
    setUp = extras.PlanExtrasChecks.setUp
    command = extras.PlanExtrasChecks.command
    post_command = extras.PlanExtrasChecks.post_command
    start = extras.PlanExtrasChecks.start
    spec = extras.PlanExtrasChecks.spec

    def test_a_mistake_seen_before_ends_the_loop_even_when_another_one_came_between(self):
        calls = []

        def verification(packet):
            ac = packet['acceptance_criterion']['id']
            calls.append(1)
            relative_missing = dict(id='OWN-2', ac_ids=[ac], kind='file', path='/abs/path.py', expect=dict(exists=True))
            bad_tool = dict(id='OWN-1', ac_ids=[ac], kind='command', argv=['curl', 'x'], expect=dict(exit=0))
            return dict(checks=[relative_missing] if len(calls) % 2 else [bad_tool, relative_missing], manual_reason=None)
        run_id = self.start(extras.Scripted(verification=verification))
        asyncio.run(self.worker.tick())
        snapshot = self.store.snapshot(run_id)
        self.assertEqual((snapshot['state'], len(calls)), ('needs_input', 3), snapshot.get('reason'))   # A, B, then A again is the repeat

    def test_the_correction_fragment_loop_also_stops_on_a_returning_mistake(self):
        wrong_a = [dict(field='goal', previous_digest='sha256:' + '0' * 64, quote=CorrectionFeedback.SCOPE_NOTE)]
        calls = []

        class Flipper(extras.Scripted):
            async def generate(inner, packet, schema):
                if packet.get('step') is None and packet.get('fragment_index') == 1:
                    calls.append(1)
                    if len(calls) % 2:
                        return dict(copy.deepcopy(extras.BASE), revisions=wrong_a)                       # a revision that does not match
                    return dict(copy.deepcopy(extras.BASE), features=['목록'], revisions=[])         # a requirement dropped without proof
                return await super().generate(packet, schema)
        run_id = self.start(Flipper())
        asyncio.run(self.worker.tick())
        snapshot = self.store.snapshot(run_id)
        self.post_command(self.command(snapshot, 'request_changes', dict(scope='spec', feedback=CorrectionFeedback.SCOPE_NOTE)))
        asyncio.run(self.worker.tick())
        self.assertEqual((self.store.snapshot(run_id)['state'], len(calls)), ('needs_input', 3))


class CorrectionFeedback(unittest.TestCase):
    """The correction fragment gets the same treatment as every other planning step: the reasons for a rejected answer go back to the
    model, and only the same mistake twice stops for the user. The proof rules for retiring a requirement are unchanged (CT40)."""
    setUp = extras.PlanExtrasChecks.setUp
    command = extras.PlanExtrasChecks.command
    post_command = extras.PlanExtrasChecks.post_command
    start = extras.PlanExtrasChecks.start
    spec = extras.PlanExtrasChecks.spec
    SCOPE_NOTE = '이번 앱에는 AI/Data 기능이 필요 없습니다.'

    def replan(self, answers):
        """Plan once, then send a scope-only correction; `answers` are the revisions the model returns for the correction fragment, in order."""
        class Reviser(extras.Scripted):
            def __init__(inner):
                super().__init__()
                inner.fragment_calls = []

            async def generate(inner, packet, schema):
                if packet.get('step') is None and packet.get('fragment_index') == 1:
                    inner.fragment_calls.append(packet)
                    revisions = answers[min(len(inner.fragment_calls), len(answers)) - 1]
                    return dict(copy.deepcopy(extras.BASE), revisions=revisions(packet) if callable(revisions) else revisions)
                return await super().generate(packet, schema)
        model = Reviser()
        run_id = self.start(model)
        asyncio.run(self.worker.tick())
        snapshot = self.store.snapshot(run_id)
        self.assertEqual(self.post_command(self.command(snapshot, 'request_changes', dict(scope='spec', feedback=self.SCOPE_NOTE))).status_code, 202)
        asyncio.run(self.worker.tick())
        return run_id, model

    def test_a_wrong_citation_is_returned_to_the_model_and_a_corrected_answer_goes_through(self):
        bad = [dict(field='goal', previous_digest='sha256:' + '0' * 64, quote=self.SCOPE_NOTE)]
        run_id, model = self.replan([bad, []])
        self.assertEqual(self.store.snapshot(run_id)['state'], 'awaiting_plan_approval')
        self.assertEqual(len(model.fragment_calls), 2)
        self.assertNotIn('previous_errors', model.fragment_calls[0])
        self.assertIn('정정 근거', ' '.join(model.fragment_calls[1]['previous_errors']))

    def test_the_same_mistake_twice_still_stops_for_the_user(self):
        bad = [dict(field='goal', previous_digest='sha256:' + '0' * 64, quote=self.SCOPE_NOTE)]
        run_id, model = self.replan([bad])
        self.assertEqual(self.store.snapshot(run_id)['state'], 'needs_input')
        self.assertEqual(len(model.fragment_calls), 2)
        self.assertTrue([r for r in self.store.model_outputs(run_id) if r['kind'] == 'rejected' and r['step'] == 'plan'])

    def test_dropping_a_requirement_without_proof_is_still_refused(self):
        class Dropper(extras.Scripted):
            async def generate(inner, packet, schema):
                if packet.get('step') is None and packet.get('fragment_index') == 1:
                    return dict(copy.deepcopy(extras.BASE), features=['목록'], revisions=[])      # '상세' vanished, nothing cites why
                return await super().generate(packet, schema)
        run_id = self.start(Dropper())
        asyncio.run(self.worker.tick())
        snapshot = self.store.snapshot(run_id)
        self.post_command(self.command(snapshot, 'request_changes', dict(scope='spec', feedback=self.SCOPE_NOTE)))
        asyncio.run(self.worker.tick())
        after = self.store.snapshot(run_id)
        self.assertEqual(after['state'], 'needs_input')
        self.assertIn('정정 근거 없이 누락', after['reason'])


if __name__ == '__main__':
    unittest.main()
