"""F2: Supervisor-side validation of a model-proposed work plan and verification specs (no model involved)."""
import unittest

from runner.plan_checks import (check_verification, check_work_plan, scopes_overlap, unverified_acceptance)

AC = [dict(id='AC1', title='첫째', description='첫째 조건'), dict(id='AC2', title='둘째', description='둘째 조건')]


def item(name, kind='backend', depends=(), acs=('AC1',), scope=('app/**',)):
    return dict(id=name, kind=kind, title=name, depends_on=list(depends), acceptance_ids=list(acs), write_scope=list(scope))


def full_plan():
    return [item('c1', 'contract', (), ('AC1', 'AC2'), ('contract/**',)),
            item('b1', 'backend', ('c1',), ('AC1',), ('server/**',)),
            item('f1', 'frontend', ('c1',), ('AC2',), ('web/**',)),
            item('i1', 'integration', ('b1', 'f1'), ('AC1', 'AC2'), ('integration/**',))]


OMITTED = [dict(kind='infra', reason='별도 인프라 없음'), dict(kind='ai_data', reason='모델이나 데이터 가공이 필요하지 않음')]


def http(name, acs):
    return dict(id=name, ac_ids=list(acs), kind='http', steps=[dict(method='GET', path='/health', expect=dict(status=200))])


class WorkPlanChecks(unittest.TestCase):
    def errors(self, plan, omitted=OMITTED, acceptance=AC):
        return check_work_plan(plan, omitted, acceptance)

    def test_a_consistent_plan_has_no_errors(self):
        self.assertEqual(self.errors(full_plan()), [])

    def test_duplicate_ids_unknown_and_self_dependencies_are_refused(self):
        plan = full_plan()
        plan.append(item('b1'))
        self.assertTrue(any('중복' in e for e in self.errors(plan)))
        plan = full_plan()
        plan[1]['depends_on'] = ['ghost']
        self.assertTrue(any('없는 작업' in e for e in self.errors(plan)))
        plan = full_plan()
        plan[1]['depends_on'] = ['b1']
        self.assertTrue(any('순환' in e for e in self.errors(plan)))

    def test_dependency_cycles_are_refused(self):
        plan = [item('a', depends=('b',), scope=('a/**',)), item('b', depends=('c',), scope=('b/**',)), item('c', depends=('a',), scope=('c/**',))]
        self.assertTrue(any('순환' in e for e in self.errors(plan, omitted=[dict(kind=k, reason='x') for k in ('infra', 'frontend', 'ai_data')])))

    def test_every_acceptance_criterion_needs_a_work_item_and_unknown_ids_are_refused(self):
        plan = full_plan()
        for entry in plan:
            entry['acceptance_ids'] = ['AC1']
        self.assertTrue(any('AC2' in e and '작업에 연결' in e for e in self.errors(plan)))
        plan = full_plan()
        plan[1]['acceptance_ids'] = ['AC9']
        self.assertTrue(any('AC9' in e for e in self.errors(plan)))

    def test_unordered_items_may_not_own_overlapping_paths_but_ordered_ones_may(self):
        plan = full_plan()
        plan[2]['write_scope'] = ['server/api/**']      # frontend vs backend, no dependency between them
        self.assertTrue(any('쓰기 범위가 겹' in e for e in self.errors(plan)))
        plan = full_plan()
        plan[3]['write_scope'] = ['server/**']          # integration runs after backend: sequential, allowed
        self.assertEqual(self.errors(plan), [])

    def test_scope_overlap_is_conservative(self):
        self.assertTrue(scopes_overlap('**', 'app/x.py'))
        self.assertTrue(scopes_overlap('app/**', 'app/api/**'))
        self.assertTrue(scopes_overlap('app/a.py', 'app/**'))
        self.assertFalse(scopes_overlap('app/a.py', 'app/b.py'))
        self.assertFalse(scopes_overlap('server/**', 'web/**'))

    def test_every_area_is_either_planned_or_omitted_with_a_reason(self):
        self.assertTrue(any('ai_data' in e for e in self.errors(full_plan(), omitted=[dict(kind='infra', reason='x')])))
        self.assertTrue(any('infra' in e for e in self.errors(full_plan(), omitted=[dict(kind='ai_data', reason='x')])))
        plan = full_plan() + [item('d1', 'ai_data', ('c1',), ('AC1',), ('data/**',))]
        self.assertTrue(any('ai_data' in e and '생략' in e for e in self.errors(plan)))   # planned and omitted at once

    def test_empty_plan_is_an_error(self):
        self.assertTrue(self.errors([]))


class VerificationChecks(unittest.TestCase):
    def errors(self, verification, manual=(), acceptance=AC):
        return check_verification(verification, list(manual), acceptance)

    def test_valid_specs_have_no_errors(self):
        inline = ['python', '-c', 'from reverse import reverse; assert reverse("abc") == "cba"']
        specs = [http('h1', ['AC1']), dict(id='c1', ac_ids=['AC2'], kind='command', argv=inline, expect=dict(exit=0)),
                 dict(id='f1', ac_ids=['AC2'], kind='file', path='README.md', expect=dict(exists=True))]
        self.assertEqual(self.errors(specs), [])

    def test_command_specs_obey_the_command_policy(self):
        bad = dict(id='c1', ac_ids=['AC1'], kind='command', argv=['sh', '-c', 'true'], expect=dict(exit=0))
        self.assertTrue(any('c1' in e for e in self.errors([bad])))
        bad = dict(id='c2', ac_ids=['AC1'], kind='command', argv=['npm', 'install'], expect=dict(exit=0))
        self.assertTrue(any('c2' in e for e in self.errors([bad])))
        bad = dict(id='c3', ac_ids=['AC1'], kind='command', argv=['python'], cwd='..', expect=dict(exit=0))
        self.assertTrue(any('c3' in e for e in self.errors([bad])))

    def test_command_checks_must_be_self_contained_inline_code(self):
        # a check that runs builder-written tests would pass a build whose tests never touch the implementation
        def bad(argv):
            return self.errors([dict(id='c9', ac_ids=['AC1'], kind='command', argv=argv, expect=dict(exit=0))])
        for argv in (['python', '-m', 'pytest'], ['python', '-m', 'unittest', 'discover'], ['python3', '-m', 'unittest'], ['node', '--test'],
                     ['npm', 'test'], ['npm', 'run', 'test'], ['python', 'tests/test_a.py'], ['node', 'a.test.js'], ['python', 'check.py'],
                     ['node', 'server.js'], ['python', '-c', 'import unittest; unittest.main()'], ['python', '-c', 'import test_reverse'],
                     ['python', '-c', 'import reverse_test'], ['python', '-c', 'import pytest; pytest.main()'], ['python', '-c'],
                     ['node', '-e', 'require("./a.test.js")']):
            errors = bad(argv)
            self.assertTrue(any('c9' in e and '자기 완결' in e for e in errors), argv)
        for argv in (['python', '-c', 'from reverse import reverse; assert reverse("ab") == "ba"'],
                     ['python3', '-c', 'import json, os; print(json.dumps({}))'], ['node', '-e', 'const f = require("./reverse"); if (f("ab") !== "ba") process.exit(1)'],
                     ['node', '--eval', 'process.exit(0)']):
            self.assertEqual(bad(argv), [], argv)

    def test_file_specs_stay_inside_the_workspace(self):
        bad = dict(id='f1', ac_ids=['AC1'], kind='file', path='../etc/passwd', expect=dict(exists=True))
        self.assertTrue(any('f1' in e for e in self.errors([bad])))

    def test_ids_and_acceptance_references_must_be_real(self):
        self.assertTrue(any('중복' in e for e in self.errors([http('h1', ['AC1']), http('h1', ['AC2'])])))
        self.assertTrue(any('AC9' in e for e in self.errors([http('h1', ['AC9'])])))
        self.assertTrue(any('AC9' in e for e in self.errors([], manual=[dict(ac_id='AC9', reason='사람 확인')])))

    def test_acceptance_without_check_or_manual_marking_is_reported(self):
        self.assertEqual(unverified_acceptance(AC, [http('h1', ['AC1'])], []), ['AC2'])
        self.assertEqual(unverified_acceptance(AC, [http('h1', ['AC1'])], [dict(ac_id='AC2', reason='시각 품질')]), [])
        self.assertEqual(unverified_acceptance(AC, [], []), ['AC1', 'AC2'])


if __name__ == '__main__':
    unittest.main()
