"""Review H-3: GREEN needs tests that actually ran, and no command can change the workspace outside the tool ledger."""
import unittest
from pathlib import Path

from backend.contracts import DomainError
from runner.commands import DockerExecutor, validate_test_command
from runner.intervention import unledgered
from runner.tdd_gate import NO_TESTS_RAN, can_finish, count_tests, progress
import test_tdd_gate as gate

IMAGE = 'python@sha256:' + 'a' * 64


def green_without_tests():
    return dict(gate.tests(0), error_code=NO_TESTS_RAN)


class CountTests(unittest.TestCase):
    def test_the_runners_summaries_are_read(self):
        cases = [('', 'Ran 3 tests in 0.002s\n\nOK\n', 3), ('', 'Ran 0 tests in 0.000s\n\nNO TESTS RAN\n', 0),
                 ('===== 2 passed, 1 warning in 0.05s =====', '', 2), ('===== no tests ran in 0.01s =====', '', 0),
                 ('# tests 4\n# suites 0\n# pass 4\n# fail 0\n', '', 4), ('Tests:       1 failed, 2 passed, 3 total', '', 2),
                 ('  5 passing (10ms)', '', 5), ('usage: pytest [options]', '', None)]
        for out, err, expected in cases:
            self.assertEqual(count_tests(out, err), expected, (out, err))


class GreenNeedsExecutedTests(unittest.TestCase):
    def test_a_pass_that_ran_no_tests_is_not_green(self):
        entries = [gate.write('tests/t.py'), gate.tests(1), gate.write('server/main.py'), green_without_tests()]
        self.assertEqual(progress(entries, 'backend').phase, 'impl')
        self.assertFalse(can_finish(entries, 'backend')[0])
        self.assertIn('실행된 테스트', progress(entries, 'backend').message)
        self.assertTrue(can_finish(entries[:-1] + [gate.tests(0)], 'backend')[0])

    def test_such_a_pass_does_not_count_as_red_either(self):
        self.assertEqual(progress([gate.write('tests/t.py'), green_without_tests()], 'backend').phase, 'red')

    def test_integration_work_also_needs_executed_tests(self):
        entries = [gate.write('integration/flow.py'), green_without_tests()]
        self.assertFalse(can_finish(entries, 'integration')[0])
        self.assertTrue(can_finish([gate.write('integration/flow.py'), gate.tests(0)], 'integration')[0])

    def test_help_and_listing_flags_are_not_a_test_run(self):
        for flag in ('-h', '--help', '--version', '--collect-only'):
            with self.assertRaises(DomainError, msg=flag):
                validate_test_command(['python', '-m', 'pytest', flag])
        validate_test_command(['python', '-m', 'unittest', 'discover'])


class WorkspaceChangesOnlyThroughTheLedger(unittest.TestCase):
    def args(self, deps_writable=False):
        return DockerExecutor(IMAGE).build_args('n', Path('/tmp/w'), ['python', '-c', 'pass'], '.', 'none', None, Path('/tmp/d'), deps_writable)

    def test_the_workspace_is_mounted_read_only_for_every_command(self):
        mounts = [a for a in self.args() if a.startswith('type=bind')]
        work = next(m for m in mounts if 'dst=/work' in m)
        self.assertTrue(work.endswith(',readonly'), work)

    def test_only_the_dependency_directory_can_be_written_and_only_when_installing(self):
        deps = lambda args: next(a for a in args if 'dst=/deps' in a)
        self.assertTrue(deps(self.args()).endswith(',readonly'))
        self.assertFalse(deps(self.args(True)).endswith(',readonly'))

    def test_a_task_that_ran_commands_is_still_blamed_for_unledgered_files(self):
        calls = [dict(tool='write_file', ok=True, args=dict(path='a.py')), dict(tool='run_tests', ok=True, args=dict(argv=['pytest']))]
        self.assertEqual(unledgered(['a.py', 'generated.txt'], calls), ['generated.txt'])


if __name__ == '__main__':
    unittest.main()
