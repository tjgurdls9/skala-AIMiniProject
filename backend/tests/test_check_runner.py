"""F2: declarative checks are evaluated mechanically; a model's claim never decides a verdict."""
import unittest

from runner.check_runner import acceptance_verdicts, evaluate, subset
from runner.commands import CommandResult


class FakeEnv:
    def __init__(self, responses=None, files=None, result=None):
        self.responses, self.files = responses or {}, files or {}
        self.result = result or CommandResult(0, 'all tests passed\n', '', False, False)
        self.http_calls, self.runs = [], []

    def http(self, method, path, body=None):
        self.http_calls.append((method, path, body))
        value = self.responses.get((method, path))
        if isinstance(value, Exception):
            raise value
        return value or (404, None)

    def run(self, argv, cwd, timeout):
        self.runs.append((argv, cwd))
        return self.result

    def read_text(self, path):
        return self.files.get(path)


def http_check(*steps, name='h1', acs=('AC1',)):
    return dict(id=name, ac_ids=list(acs), kind='http', steps=list(steps))


def step(method='GET', path='/health', status=200, **extra):
    return dict(method=method, path=path, expect=dict(status=status, **extra))


class SubsetChecks(unittest.TestCase):
    def test_dicts_lists_and_scalars(self):
        self.assertTrue(subset({'a': 1}, {'a': 1, 'b': 2}))
        self.assertFalse(subset({'a': 2}, {'a': 1}))
        self.assertFalse(subset({'c': 1}, {'a': 1}))
        self.assertTrue(subset([{'id': 1}], [{'id': 0, 'x': 1}, {'id': 1, 'y': 2}]))   # every expected element appears somewhere
        self.assertFalse(subset([{'id': 9}], [{'id': 1}]))
        self.assertTrue(subset('ok', 'ok'))
        self.assertFalse(subset('ok', None))
        self.assertTrue(subset(True, True))
        self.assertFalse(subset(1, True))      # bool is not an integer here


class EvaluateChecks(unittest.TestCase):
    def test_http_passes_only_on_the_expected_status_and_body_subset(self):
        env = FakeEnv({('GET', '/health'): (200, {'status': 'ok', 'extra': 1})})
        self.assertEqual(evaluate(http_check(step(json_subset={'status': 'ok'})), env).status, 'passed')
        self.assertEqual(evaluate(http_check(step(json_subset={'status': 'down'})), env).status, 'failed')
        self.assertEqual(evaluate(http_check(step(status=201)), env).status, 'failed')

    def test_http_steps_run_in_order_and_stop_at_the_first_failure(self):
        env = FakeEnv({('POST', '/items'): (500, None), ('GET', '/items'): (200, [])})
        outcome = evaluate(http_check(step('POST', '/items', 201), step('GET', '/items', 200)), env)
        self.assertEqual(outcome.status, 'failed')
        self.assertEqual(env.http_calls, [('POST', '/items', None)])

    def test_connection_errors_are_tool_errors_not_failures_of_the_app_claim(self):
        env = FakeEnv({('GET', '/health'): OSError('refused')})
        self.assertEqual(evaluate(http_check(step()), env).status, 'error')

    def test_command_checks_compare_exit_code_and_output(self):
        spec = dict(id='c1', ac_ids=['AC1'], kind='command', argv=['python', '-m', 'pytest'],
                    expect=dict(exit=0, stdout_contains=['passed']))
        self.assertEqual(evaluate(spec, FakeEnv()).status, 'passed')
        failing = FakeEnv(result=CommandResult(1, 'boom', '', False, False))
        self.assertEqual(evaluate(spec, failing).status, 'failed')
        silent = FakeEnv(result=CommandResult(0, 'ok', '', False, False))
        self.assertEqual(evaluate(spec, silent).status, 'failed')
        timed_out = FakeEnv(result=CommandResult(None, '', '', True, False))
        self.assertEqual(evaluate(spec, timed_out).status, 'failed')

    def test_file_checks(self):
        env = FakeEnv(files={'README.md': 'hello world'})
        spec = lambda **expect: dict(id='f1', ac_ids=['AC1'], kind='file', path='README.md', expect=expect)
        self.assertEqual(evaluate(spec(exists=True, contains=['hello']), env).status, 'passed')
        self.assertEqual(evaluate(spec(exists=True, contains=['absent']), env).status, 'failed')
        self.assertEqual(evaluate(spec(exists=False), env).status, 'failed')
        missing = dict(id='f2', ac_ids=['AC1'], kind='file', path='nope.txt', expect=dict(exists=False))
        self.assertEqual(evaluate(missing, env).status, 'passed')

    def test_outcome_carries_no_model_text_only_observed_evidence(self):
        env = FakeEnv({('GET', '/health'): (200, {'status': 'ok'})})
        outcome = evaluate(http_check(step()), env)
        self.assertEqual(outcome.id, 'h1')
        self.assertEqual(outcome.evidence['steps'][0]['status'], 200)


class VerdictChecks(unittest.TestCase):
    AC = [dict(id='AC1', title='a', description='a'), dict(id='AC2', title='b', description='b'), dict(id='AC3', title='c', description='c')]

    def verdicts(self, specs, outcomes, manual=()):
        return {v['id']: v for v in acceptance_verdicts(self.AC, specs, list(manual), outcomes)}

    def outcome(self, name, status):
        from runner.check_runner import CheckOutcome
        return CheckOutcome(name, status, '', {})

    def test_met_needs_every_linked_check_to_pass(self):
        specs = [http_check(name='h1', acs=['AC1']), http_check(name='h2', acs=['AC1', 'AC2'])]
        verdicts = self.verdicts(specs, [self.outcome('h1', 'passed'), self.outcome('h2', 'passed')])
        self.assertEqual((verdicts['AC1']['status'], verdicts['AC2']['status']), ('met', 'met'))
        verdicts = self.verdicts(specs, [self.outcome('h1', 'passed'), self.outcome('h2', 'failed')])
        self.assertEqual((verdicts['AC1']['status'], verdicts['AC2']['status']), ('unmet', 'unmet'))

    def test_errors_missing_results_and_unchecked_criteria_never_count_as_met(self):
        specs = [http_check(name='h1', acs=['AC1']), http_check(name='h2', acs=['AC2'])]
        verdicts = self.verdicts(specs, [self.outcome('h1', 'error')])
        self.assertEqual(verdicts['AC1']['status'], 'failed')       # the tool broke
        self.assertEqual(verdicts['AC2']['status'], 'not_run')      # never executed
        self.assertEqual(verdicts['AC3']['status'], 'not_run')      # nothing checks it

    def test_failure_beats_error_and_manual_marking_stays_not_run(self):
        specs = [http_check(name='h1', acs=['AC1']), http_check(name='h2', acs=['AC1'])]
        verdicts = self.verdicts(specs, [self.outcome('h1', 'failed'), self.outcome('h2', 'error')],
                                 manual=[dict(ac_id='AC3', reason='시각 품질')])
        self.assertEqual(verdicts['AC1']['status'], 'unmet')
        self.assertEqual(verdicts['AC3']['status'], 'not_run')
        self.assertEqual(verdicts['AC3']['reason'], 'manual')
        self.assertEqual(verdicts['AC1']['check_ids'], ['h1', 'h2'])


if __name__ == '__main__':
    unittest.main()
