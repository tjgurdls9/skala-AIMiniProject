"""F3: the server decides RED and GREEN from the tool ledger's real exit codes; the model's words never count."""
import unittest

from runner.tdd_gate import can_finish, is_test_path, progress


def write(path, ok=True):
    return dict(tool='write_file', ok=ok, args=dict(path=path), exit_code=None)


def delete(path):
    return dict(tool='delete_file', ok=True, args=dict(path=path), exit_code=None)


def move(source, target):
    return dict(tool='move_file', ok=True, args=dict(source=source, target=target), exit_code=None)


def tests(code, ok=True):
    return dict(tool='run_tests', ok=ok, args=dict(argv=['python', '-m', 'pytest']), exit_code=code)


def phase(entries, kind='backend'):
    return progress(entries, kind).phase


class TestPathChecks(unittest.TestCase):
    def test_conventional_test_locations_are_recognised(self):
        for path in ('tests/a.py', 'pkg/tests/b.py', 'test_x.py', 'pkg/test_x.py', 'pkg/x_test.py', 'web/a.test.js', 'web/a.spec.ts',
                     'web/__tests__/a.js', 'a/b.test.mjs'):
            self.assertTrue(is_test_path(path), path)
        for path in ('server/main.py', 'web/app.js', 'contest.py', 'latest/x.py', 'docs/testing.md'):
            self.assertFalse(is_test_path(path), path)


class TddProgress(unittest.TestCase):
    def test_nothing_is_green_before_a_real_failing_run_of_new_tests(self):
        self.assertEqual(phase([]), 'red')
        self.assertEqual(phase([tests(1)]), 'red')                                 # failing run but no tests written yet
        self.assertEqual(phase([write('tests/t.py')]), 'red')                     # tests written, never run
        self.assertEqual(phase([write('tests/t.py'), tests(0)]), 'red')           # tests that pass immediately are not RED
        self.assertEqual(phase([write('tests/t.py'), tests(None)]), 'red')        # a timeout is not a failing test

    def test_red_then_implementation_then_green(self):
        entries = [write('tests/t.py'), tests(1)]
        self.assertEqual(phase(entries), 'impl')
        entries.append(tests(0))                                                   # passing without any implementation write
        self.assertEqual(phase(entries), 'impl')
        entries += [write('server/main.py'), tests(0)]
        self.assertEqual(phase(entries), 'done')
        self.assertEqual(can_finish(entries, 'backend'), (True, ''))

    def test_failed_writes_and_denied_calls_do_not_advance_anything(self):
        self.assertEqual(phase([write('tests/t.py', ok=False), tests(1)]), 'red')
        self.assertEqual(phase([write('tests/t.py'), tests(1, ok=False)]), 'red')

    def test_fixing_a_test_after_red_is_allowed_and_does_not_reset_the_gate(self):
        # real runs: a test that failed for the wrong reason (a missing import) must be fixable without a second failure
        entries = [write('tests/t.py'), tests(1), write('tests/t.py')]
        self.assertEqual(phase(entries), 'impl')
        self.assertEqual(phase(entries + [delete('tests/t.py')]), 'impl')
        self.assertEqual(phase(entries + [move('tests/t.py', 'tests/u.py')]), 'impl')

    def test_green_needs_an_implementation_file_outside_the_test_paths_and_a_pass_after_the_last_change(self):
        fixed_test_only = [write('tests/t.py'), tests(1), write('tests/t.py'), tests(0)]
        self.assertEqual(phase(fixed_test_only), 'impl')                       # no implementation file was written
        self.assertFalse(can_finish(fixed_test_only, 'backend')[0])
        self.assertIn('테스트 경로 밖', progress(fixed_test_only, 'backend').message)
        entries = [write('tests/t.py'), tests(1), write('server/main.py'), write('tests/t.py'), tests(0)]
        self.assertEqual(phase(entries), 'done')                               # the test fix came before the passing run
        self.assertEqual(phase(entries[:-1]), 'impl')                          # the pass must follow the last change

    def test_any_change_after_green_needs_a_new_passing_run_but_keeps_the_implementation_credit(self):
        entries = [write('tests/t.py'), tests(1), write('server/main.py'), tests(0)]
        self.assertEqual(phase(entries + [write('tests/t.py')]), 'impl')
        self.assertEqual(phase(entries + [write('server/main.py')]), 'impl')
        self.assertEqual(phase(entries + [write('tests/t.py'), tests(1)]), 'impl')
        self.assertEqual(phase(entries + [write('tests/t.py'), tests(0)]), 'done')

    def test_finish_is_refused_with_a_reason_until_done(self):
        ok, reason = can_finish([write('tests/t.py'), tests(1), write('server/main.py')], 'backend')
        self.assertFalse(ok)
        self.assertIn('테스트', reason)
        ok, reason = can_finish([], 'frontend')
        self.assertFalse(ok)


class GateMessages(unittest.TestCase):
    def message(self, entries):
        return progress(entries, 'backend').message

    def test_each_state_names_what_to_do_next(self):
        self.assertIn('실패하는 테스트', self.message([]))
        self.assertIn('run_tests', self.message([write('tests/t.py')]))
        self.assertIn('바로 통과', self.message([write('tests/t.py'), tests(0)]))
        self.assertIn('시간 초과', self.message([write('tests/t.py'), tests(None)]))
        self.assertIn('구현 파일을 작성', self.message([write('tests/t.py'), tests(1)]))
        self.assertIn('run_tests', self.message([write('tests/t.py'), tests(1), write('server/main.py')]))
        self.assertIn('아직 실패', self.message([write('tests/t.py'), tests(1), write('server/main.py'), tests(1)]))
        self.assertIn('finish', self.message([write('tests/t.py'), tests(1), write('server/main.py'), tests(0)]))


class OtherKinds(unittest.TestCase):
    def test_contract_and_infra_tasks_have_no_test_phase_but_must_change_something(self):
        for kind in ('contract', 'infra'):
            self.assertEqual(phase([], kind), 'free')
            self.assertFalse(can_finish([], kind)[0])
            self.assertTrue(can_finish([write('contract/api.json')], kind)[0])
            self.assertFalse(can_finish([write('contract/api.json', ok=False)], kind)[0])

    def test_integration_must_end_with_a_passing_test_run_after_its_last_change(self):
        self.assertFalse(can_finish([write('integration/flow.py')], 'integration')[0])
        self.assertFalse(can_finish([write('integration/flow.py'), tests(1)], 'integration')[0])
        self.assertTrue(can_finish([write('integration/flow.py'), tests(0)], 'integration')[0])
        self.assertFalse(can_finish([write('integration/flow.py'), tests(0), write('integration/flow.py')], 'integration')[0])


if __name__ == '__main__':
    unittest.main()
