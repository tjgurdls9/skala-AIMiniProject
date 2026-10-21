"""F2: the model-driven planning extras (alternatives, work plan, verification) end to end with a scripted fake model.

The blank starter has no feature code; every plan field below comes from the scripted model, never from the service.
"""
import asyncio
import copy
import json
import unittest

from backend.contracts import DomainError, canonical, digest, validate
from runner.commands import tool_policy_digest
import test_runtime as fixtures

BASE = dict(goal='요청 처리 서비스', features=['목록', '상세'], non_goals=[], constraints=['무료만'], assumptions=['합성 데이터'],
            changes=[], acceptance=[dict(id='AC1', title='목록', description='목록이 보인다'),
                                    dict(id='AC2', title='상세', description='상세가 보인다')])
ALTERNATIVES = [dict(id='A', summary='현재 기획', differences='기준안', risks='범위가 넓음'),
                dict(id='B', summary='목록만 먼저', differences='상세는 후속', risks='가치가 작음')]


def plan_items():
    return [dict(id='c1', kind='contract', title='계약', depends_on=[], acceptance_ids=['AC1', 'AC2'], write_scope=['contract/**']),
            dict(id='b1', kind='backend', title='서버', depends_on=['c1'], acceptance_ids=['AC1', 'AC2'], write_scope=['server/**']),
            dict(id='f1', kind='frontend', title='화면', depends_on=['c1'], acceptance_ids=['AC1', 'AC2'], write_scope=['web/**']),
            dict(id='i1', kind='integration', title='통합', depends_on=['b1', 'f1'], acceptance_ids=['AC1'], write_scope=['integration/**'])]


def http_check(ac):
    return dict(id='x', ac_ids=[ac], kind='http', steps=[dict(method='GET', path='/health', expect=dict(status=200))])


class Scripted(fixtures.FakeModel):
    """Answers each planning step; `overrides` lets a test replace one step's answer."""
    def __init__(self, **overrides):
        self.calls, self.overrides = [], overrides

    async def generate(self, packet, schema):
        self.calls.append(packet)
        step = packet.get('step')
        if step in self.overrides:
            value = self.overrides[step]
            return copy.deepcopy(value(packet) if callable(value) else value)
        if step == 'alternatives':
            return dict(alternatives=copy.deepcopy(ALTERNATIVES))
        if step == 'work_plan':
            return dict(work_plan=plan_items(), omitted_areas=[dict(kind='infra', reason='추가 인프라 없음'),
                                                                dict(kind='ai_data', reason='모델이 필요하지 않음')],
                        dependencies=dict(pip=['fastapi'], npm=[]))
        if step == 'verification':
            ac = packet['acceptance_criterion']['id']
            return dict(checks=[dict(http_check(ac), ac_ids=[ac])], manual_reason=None)
        return copy.deepcopy(BASE)

    def steps(self):
        return [c.get('step', 'plan') for c in self.calls]


class PlanExtrasChecks(unittest.TestCase):
    setUp = fixtures.RuntimeChecks.setUp
    command = fixtures.RuntimeChecks.command
    post_command = fixtures.RuntimeChecks.post_command

    def start(self, model, request='generic request'):
        self.worker.model = model
        self.worker.heartbeat()
        project = self.store.project(dict(title='generic', request=request))
        return self.store.create_run(project['project_id'], dict(mode='live'), template_id='blank-v1')['run_id']

    def spec(self, run_id):
        snapshot = self.store.snapshot(run_id)
        artifact = next(a for a in reversed(snapshot['artifacts']) if a['kind'] == 'spec')
        return snapshot, self.store.read_artifact(artifact['id'])

    def test_plan_carries_alternatives_work_plan_and_checks_and_is_approvable(self):
        model = Scripted()
        run_id = self.start(model)
        asyncio.run(self.worker.tick())
        snapshot, plan = self.spec(run_id)
        validate('PlanView', plan)
        self.assertEqual(snapshot['state'], 'awaiting_plan_approval')
        self.assertEqual([a['id'] for a in plan['alternatives']], ['A', 'B'])
        self.assertEqual(plan['selected_alternative_id'], 'A')
        self.assertEqual([i['id'] for i in plan['work_plan']], ['c1', 'b1', 'f1', 'i1'])
        self.assertEqual(sorted(a for v in plan['verification'] for a in v['ac_ids']), ['AC1', 'AC2'])
        self.assertEqual(len({v['id'] for v in plan['verification']}), 2)   # ids are made unique by the service
        self.assertEqual(plan['dependencies'], dict(pip=['fastapi'], npm=[]))
        self.assertEqual(plan['tool_policy_digest'], tool_policy_digest())  # server computed, never the model
        self.assertTrue(plan['support']['implementation_allowed'])
        self.assertEqual(model.steps().count('alternatives'), 1)
        self.assertEqual(model.steps().count('verification'), 2)             # one small call per acceptance criterion

    def test_tasks_come_from_the_approved_work_plan_with_dependencies_and_scopes(self):
        run_id = self.start(Scripted())
        asyncio.run(self.worker.tick())
        snapshot, plan = self.spec(run_id)
        builders = [t for t in snapshot['tasks'] if t['role'] == 'builder']
        self.assertEqual([t['title'] for t in builders], ['계약', '서버', '화면', '통합'])
        by_title = {t['title']: t for t in builders}
        self.assertEqual(set(by_title['통합']['depends_on']), {by_title['서버']['id'], by_title['화면']['id']})
        self.assertEqual(by_title['계약']['state'], 'ready')
        self.assertEqual(by_title['서버']['state'], 'pending')
        self.assertEqual({t['work_kind'] for t in builders}, {'contract', 'backend', 'frontend', 'integration'})
        with self.store.transaction() as db:
            scopes = {r[0]: json.loads(r[1]) for r in db.execute('SELECT task_id, files FROM task_scopes')}
        self.assertEqual(scopes[by_title['서버']['id']], ['server/**'])

    def test_acceptance_without_a_check_blocks_approval_until_it_is_marked_for_a_human(self):
        def verification(packet):
            ac = packet['acceptance_criterion']['id']
            return dict(checks=[], manual_reason=None) if ac == 'AC2' else dict(checks=[http_check(ac)], manual_reason=None)
        run_id = self.start(Scripted(verification=verification))
        asyncio.run(self.worker.tick())
        snapshot, plan = self.spec(run_id)
        self.assertFalse(plan['support']['implementation_allowed'])
        self.assertIn('AC2', canonical(plan['support']['unsupported']))
        approval = snapshot['approvals'][-1]
        response = self.post_command(self.command(snapshot, 'decide', dict(approval_id=approval['id'], target_digest=approval['target_digest'], decision='approve')))
        self.assertEqual(response.status_code, 409)

        def with_manual(packet):
            ac = packet['acceptance_criterion']['id']
            return dict(checks=[], manual_reason='시각 품질은 사람이 본다') if ac == 'AC2' else dict(checks=[http_check(ac)], manual_reason=None)
        run_id = self.start(Scripted(verification=with_manual))
        asyncio.run(self.worker.tick())
        snapshot, plan = self.spec(run_id)
        self.assertTrue(plan['support']['implementation_allowed'])
        self.assertEqual(plan['manual_acceptance'], [dict(ac_id='AC2', reason='시각 품질은 사람이 본다')])

    def test_single_alternative_requires_a_reason(self):
        run_id = self.start(Scripted(alternatives=dict(alternatives=[ALTERNATIVES[0]], single_reason='요청이 한 가지 방식만 허용함')))
        asyncio.run(self.worker.tick())
        _, plan = self.spec(run_id)
        self.assertEqual([a['id'] for a in plan['alternatives']], ['A'])
        self.assertEqual(plan['single_alternative_reason'], '요청이 한 가지 방식만 허용함')
        run_id = self.start(Scripted(alternatives=dict(alternatives=[ALTERNATIVES[0]])))
        asyncio.run(self.worker.tick())
        self.assertEqual(self.store.snapshot(run_id)['state'], 'needs_input')

    def test_invalid_work_plan_is_returned_to_the_model_with_the_errors(self):
        attempts = []

        def work_plan(packet):
            attempts.append(packet.get('previous_errors'))
            plan = plan_items()
            if len(attempts) == 1:
                plan[1]['depends_on'] = ['i1']     # introduces a cycle b1 -> i1 -> b1
            return dict(work_plan=plan, omitted_areas=[dict(kind='infra', reason='x'), dict(kind='ai_data', reason='y')], dependencies={})
        run_id = self.start(Scripted(work_plan=work_plan))
        asyncio.run(self.worker.tick())
        self.assertEqual(self.store.snapshot(run_id)['state'], 'awaiting_plan_approval')
        self.assertIsNone(attempts[0])
        self.assertTrue(any('순환' in e for e in attempts[1]))

    def test_repeating_the_same_mistake_stops_for_the_user_instead_of_looping(self):
        def work_plan(packet):
            plan = plan_items()
            plan[1]['depends_on'] = ['i1']
            return dict(work_plan=plan, omitted_areas=[dict(kind='infra', reason='x'), dict(kind='ai_data', reason='y')], dependencies={})
        model = Scripted(work_plan=work_plan)
        run_id = self.start(model)
        asyncio.run(self.worker.tick())
        snapshot = self.store.snapshot(run_id)
        self.assertEqual(snapshot['state'], 'needs_input')
        self.assertEqual(model.steps().count('work_plan'), 2)   # second identical error ends the loop

    def test_choosing_another_alternative_replans_it_without_regenerating_alternatives(self):
        model = Scripted()
        run_id = self.start(model)
        asyncio.run(self.worker.tick())
        snapshot, first = self.spec(run_id)
        model.calls.clear()
        response = self.post_command(self.command(snapshot, 'request_changes', dict(scope='spec', feedback='B안으로 진행', alternative_id='B')))
        self.assertEqual(response.status_code, 202, response.text)
        asyncio.run(self.worker.tick())
        snapshot, second = self.spec(run_id)
        self.assertEqual(second['selected_alternative_id'], 'B')
        self.assertEqual(second['alternatives'], first['alternatives'])
        self.assertNotIn('alternatives', model.steps())
        plan_calls = [c for c in model.calls if 'step' not in c]
        self.assertTrue(plan_calls and all(c['selected_alternative']['id'] == 'B' for c in plan_calls))
        self.assertNotEqual(second['spec_version_id'], first['spec_version_id'])

    def test_unknown_alternative_is_refused(self):
        run_id = self.start(Scripted())
        asyncio.run(self.worker.tick())
        snapshot, _ = self.spec(run_id)
        response = self.post_command(self.command(snapshot, 'request_changes', dict(scope='spec', feedback='Z안', alternative_id='Z')))
        self.assertEqual(response.status_code, 422)

    def test_interrupted_planning_reuses_finished_extra_steps(self):
        from runner.model import ModelUnavailable

        class Flaky(Scripted):
            fail = True

            async def generate(self, packet, schema):
                if self.fail and packet.get('step') == 'verification' and packet['acceptance_criterion']['id'] == 'AC2':
                    self.calls.append(packet)
                    raise ModelUnavailable('synthetic outage')
                return await super().generate(packet, schema)
        model = Flaky()
        run_id = self.start(model)
        asyncio.run(self.worker.tick())
        self.assertNotEqual(self.store.snapshot(run_id)['state'], 'awaiting_plan_approval')
        before = model.steps()
        model.fail = False
        model.calls.clear()
        resume = self.store.snapshot(run_id)
        self.post_command(self.command(resume, 'resume'))
        asyncio.run(self.worker.tick())
        self.assertEqual(self.store.snapshot(run_id)['state'], 'awaiting_plan_approval')
        self.assertIn('alternatives', before)
        self.assertNotIn('alternatives', model.steps())
        self.assertNotIn('work_plan', model.steps())


if __name__ == '__main__':
    unittest.main()
