"""F4c: independent validation of a model-authored candidate by running the approved check specs; docker is faked."""
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from runner.check_runner import CheckOutcome
from runner.model import ModelUnavailable
from runner.review import Reviewer, model_validation_body
from runner.sandbox import Sandbox

ROOT = Path(__file__).resolve().parents[2]
IMAGE = 'sha256:' + 'a' * 64
CHECKER = 'python@sha256:' + 'b' * 64


def http_check(name='h1', acs=('AC1',), path='/items', status=200, **extra):
    return dict(id=name, ac_ids=list(acs), kind='http', steps=[dict(method='GET', path=path, expect=dict(status=status, **extra))])


class FakeEngine:
    limits = staticmethod(Sandbox.limits)

    def __init__(self, probe):
        self.probe, self.calls, self.cleaned = probe, [], []

    def docker(self, *args, timeout=120):
        self.calls.append([str(a) for a in args])
        probe = [i for i, a in enumerate(args) if str(a).endswith('http_probe.py')]
        if probe:
            i = probe[0]
            body = args[i + 4] if len(args) > i + 4 else None
            return json.dumps(self.probe(args[i + 2], args[i + 3], json.loads(body) if body else None))   # args: script, base, METHOD, PATH[, body]
        return ''

    def start_candidate(self, candidate, network, name, data_volume=None):
        self.calls.append(['start', network, name])

    def cleanup(self, name):
        self.cleaned.append(name)
        return True


class Done:
    def __init__(self, code=0, out=b'', err=b''):
        self.returncode, self.stdout, self.stderr = code, out, err


class ValidationRun(unittest.TestCase):
    def setUp(self):
        self.temp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (self.temp / 'cand').mkdir()
        (self.temp / 'cand' / 'README.md').write_text('hello world')
        self.candidate = dict(path=str(self.temp / 'cand'), image_digest=IMAGE, commit_sha='c' * 40,
                              app=dict(runtime='python', start=['python', 'app.py'], port=8080, health='/health'))
        self.runs = []

    def reviewer(self, probe, runner=None, current=lambda: True):
        def default_runner(args, **kwargs):
            self.runs.append(list(args))
            return Done(0, b'ok\n')
        self.engine = FakeEngine(probe)
        return Reviewer(self.engine, current, runner=runner or default_runner, sleep=lambda s: None)

    def validate(self, reviewer, specs):
        return reviewer.model_validation(self.candidate, specs, CHECKER)

    def test_http_checks_run_in_a_checker_container_on_the_internal_network_and_resources_are_cleaned(self):
        reviewer = self.reviewer(lambda method, path, body: dict(status=200, body={'ok': True}))
        outcomes, info = self.validate(reviewer, [http_check(), http_check('h2', path='/health')])
        self.assertEqual([o.status for o in outcomes], ['passed', 'passed'])
        self.assertTrue(info['healthy'])
        calls = self.engine.calls
        self.assertEqual(calls[0][:3], ['network', 'create', '--internal'])
        self.assertTrue(any(c[0] == 'start' for c in calls))
        probe = next(c for c in calls if any(str(a).endswith('http_probe.py') for a in c))
        self.assertIn(CHECKER, probe)
        self.assertIn('--network', probe)
        self.assertTrue(any(c[:2] == ['network', 'rm'] for c in calls))      # the internal network is removed again
        started = next(c for c in calls if c[0] == 'start')
        self.assertIn(started[2], self.engine.cleaned)                       # the app container is always removed

    def test_an_app_that_never_answers_its_health_path_fails_its_http_checks_as_an_app_defect(self):
        reviewer = self.reviewer(lambda method, path, body: dict(error='connection refused'))
        outcomes, info = self.validate(reviewer, [http_check(), dict(id='f1', ac_ids=['AC2'], kind='file', path='README.md', expect=dict(exists=True))])
        self.assertFalse(info['healthy'])
        self.assertEqual((outcomes[0].status, outcomes[1].status), ('failed', 'passed'))     # file checks do not need the app
        self.assertIn('상태 확인', outcomes[0].detail)
        self.assertLessEqual(len(self.engine.calls), 40)                                       # the wait is bounded

    def test_a_wrong_status_or_body_is_a_failed_check_not_an_error(self):
        reviewer = self.reviewer(lambda method, path, body: dict(status=200, body={'items': []}) if path == '/health' else dict(status=500, body=None))
        outcomes, _ = self.validate(reviewer, [http_check(status=200)])
        self.assertEqual(outcomes[0].status, 'failed')

    def test_command_checks_run_in_the_candidate_image_without_network_and_use_the_real_exit_code(self):
        specs = [dict(id='c1', ac_ids=['AC1'], kind='command', argv=['python', '-m', 'unittest'], expect=dict(exit=0, stdout_contains=['ok']))]
        reviewer = self.reviewer(lambda m, p, b: dict(status=200, body={}))
        outcomes, _ = self.validate(reviewer, specs)
        self.assertEqual(outcomes[0].status, 'passed')
        run = self.runs[0]
        self.assertIn(IMAGE, run)
        self.assertEqual(run[run.index('--network') + 1], 'none')
        self.assertEqual(run[-3:], ['python', '-m', 'unittest'])
        failing = self.reviewer(lambda m, p, b: dict(status=200, body={}), runner=lambda args, **kw: Done(1, b'', b'AssertionError'))
        self.assertEqual(self.validate(failing, specs)[0][0].status, 'failed')
        broken = self.reviewer(lambda m, p, b: dict(status=200, body={}), runner=lambda args, **kw: Done(125, b'', b'docker: daemon error'))
        self.assertEqual(self.validate(broken, specs)[0][0].status, 'error')       # an infrastructure code is not a verdict on the app

    def test_file_checks_read_the_candidate_checkout_and_cannot_leave_it(self):
        specs = [dict(id='f1', ac_ids=['AC1'], kind='file', path='README.md', expect=dict(exists=True, contains=['hello'])),
                 dict(id='f2', ac_ids=['AC1'], kind='file', path='missing.txt', expect=dict(exists=False)),
                 dict(id='f3', ac_ids=['AC1'], kind='file', path='../outside', expect=dict(exists=False))]
        outcomes, _ = self.validate(self.reviewer(lambda m, p, b: dict(status=200, body={})), specs)
        self.assertEqual([o.status for o in outcomes], ['passed', 'passed', 'error'])

    def test_a_superseded_attempt_stops_the_review_and_still_cleans_up(self):
        reviewer = self.reviewer(lambda m, p, b: dict(status=200, body={}), current=lambda: False)
        with self.assertRaises(ModelUnavailable):
            self.validate(reviewer, [http_check()])
        self.assertTrue(self.engine.cleaned)


class ReportBody(unittest.TestCase):
    AC = [dict(id='AC1', title='a', description='a'), dict(id='AC2', title='b', description='b')]

    def body(self, outcomes, manual=(), verification=None):
        spec = dict(acceptance=self.AC, manual_acceptance=list(manual),
                    verification=verification or [http_check('h1', ['AC1']), http_check('h2', ['AC2'])])
        return model_validation_body(spec, outcomes, dict(healthy=True))

    def outcome(self, name, status):
        return CheckOutcome(name, status, '', dict(note=name))

    def test_pass_needs_every_criterion_met_by_its_checks(self):
        body = self.body([self.outcome('h1', 'passed'), self.outcome('h2', 'passed')])
        self.assertEqual(body['verdict'], 'pass')
        self.assertEqual([(a['id'], a['status'], a['evidence']) for a in body['judgement']['acceptance']], [('AC1', 'met', ['h1']), ('AC2', 'met', ['h2'])])
        self.assertEqual(body['tools']['checks'], {'h1': True, 'h2': True})
        self.assertTrue(body['tools']['mechanical'])

    def test_a_failed_check_is_a_fail_with_the_criterion_unmet(self):
        body = self.body([self.outcome('h1', 'passed'), self.outcome('h2', 'failed')])
        self.assertEqual(body['verdict'], 'fail')
        self.assertEqual({a['id']: a['status'] for a in body['judgement']['acceptance']}, {'AC1': 'met', 'AC2': 'unmet'})
        self.assertEqual(body['tools']['checks'], {'h1': True, 'h2': False})

    def test_a_tool_error_is_an_error_verdict_never_a_pass(self):
        self.assertEqual(self.body([self.outcome('h1', 'passed'), self.outcome('h2', 'error')])['verdict'], 'error')

    def test_unchecked_or_human_confirmed_criteria_cannot_pass_automatically(self):
        only_one = self.body([self.outcome('h1', 'passed')], verification=[http_check('h1', ['AC1'])])
        self.assertEqual(only_one['verdict'], 'not_run')
        manual = self.body([self.outcome('h1', 'passed')], manual=[dict(ac_id='AC2', reason='시각')], verification=[http_check('h1', ['AC1'])])
        self.assertEqual(manual['verdict'], 'not_run')
        self.assertEqual({a['id']: a['status'] for a in manual['judgement']['acceptance']}['AC2'], 'not_run')

    def test_an_app_that_did_not_start_is_reported_in_the_summary(self):
        spec = dict(acceptance=self.AC[:1], manual_acceptance=[], verification=[http_check('h1', ['AC1'])])
        body = model_validation_body(spec, [CheckOutcome('h1', 'failed', '앱이 상태 확인에 응답하지 않았습니다.', {})], dict(healthy=False))
        self.assertEqual(body['verdict'], 'fail')
        self.assertIn('시작', body['judgement']['summary'])


class ReverseRegression(unittest.TestCase):
    """The real run: the builder's test redefined the function itself, so it passed without touching the implementation file."""
    INLINE = ['python', '-c', 'from reverse import reverse; assert reverse("abc") == "cba"']
    UNITTEST = ['python', '-m', 'unittest']

    def setUp(self):
        self.temp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (self.temp / 'cand').mkdir()
        self.candidate = dict(path=str(self.temp / 'cand'), image_digest=IMAGE, commit_sha='c' * 40,
                              app=dict(runtime='python', start=['python', 'app.py'], port=8080, health='/health'))

    def outcomes(self, specs, image_has_tests):
        def runner(args, **kwargs):
            argv = args[args.index(IMAGE) + 1:]
            if argv == self.UNITTEST:                   # builder tests that define their own reverse() pass whenever they exist
                return Done(0 if image_has_tests else 5, b'', b'OK' if image_has_tests else b'NO TESTS RAN')
            return Done(1, b'', b'AssertionError')       # the implementation file really is wrong
        reviewer = Reviewer(FakeEngine(lambda m, p, b: dict(status=200, body={})), runner=runner, sleep=lambda s: None)
        return reviewer.model_validation(self.candidate, specs, CHECKER)[0]

    def spec(self, argv):
        return dict(id='c1', ac_ids=['AC1'], kind='command', argv=argv, expect=dict(exit=0))

    def test_without_the_rule_a_check_that_runs_builder_tests_passes_a_wrong_implementation(self):
        from runner.plan_checks import check_verification
        check = self.spec(self.UNITTEST)
        self.assertEqual(self.outcomes([check], image_has_tests=True)[0].status, 'passed')      # the hole: validation would pass
        ac = [dict(id='AC1', title='a', description='a')]
        self.assertTrue(any('자기 완결' in e for e in check_verification([check], [], ac)))         # the rule closes it at planning time

    def test_with_the_rule_the_same_wrong_implementation_is_unmet_and_the_candidate_cannot_pass(self):
        from runner.plan_checks import check_verification
        check = self.spec(self.INLINE)
        ac = [dict(id='AC1', title='a', description='a')]
        self.assertEqual(check_verification([check], [], ac), [])
        outcomes = self.outcomes([check], image_has_tests=False)
        self.assertEqual(outcomes[0].status, 'failed')
        body = model_validation_body(dict(acceptance=ac, manual_acceptance=[], verification=[check]), outcomes, dict(healthy=True))
        self.assertEqual((body['verdict'], body['judgement']['acceptance'][0]['status']), ('fail', 'unmet'))

    def test_even_a_test_runner_check_finds_nothing_to_run_because_the_image_has_no_tests(self):
        self.assertEqual(self.outcomes([self.spec(self.UNITTEST)], image_has_tests=False)[0].status, 'failed')


class SecurityArguments(unittest.TestCase):
    def test_a_model_candidate_is_scanned_with_the_import_names_of_its_approved_dependencies(self):
        calls = []
        temp = Path(self.enterContext(tempfile.TemporaryDirectory()))

        class Engine(FakeEngine):
            root = temp

            def docker(self, *args, timeout=120):
                calls.append([str(a) for a in args])
                if args[0] == 'run':
                    return json.dumps(dict(checks=dict(static=True, secrets=True), findings=[]))
                if args[0] == 'inspect':
                    return json.dumps([dict(HostConfig=dict(ReadonlyRootfs=True, Privileged=False, NetworkMode='none', CapDrop=['ALL']),
                                            Config=dict(User='65534:65534'), Mounts=[dict(Destination='/checks', RW=False), dict(Destination='/candidate', RW=False)])])
                return ''
        candidate = dict(path=str(temp), image_digest=IMAGE, dependency_modules={'pyyaml': ['yaml'], 'python-dateutil': ['dateutil']})
        reviewer = Reviewer(Engine(lambda *a: {}))
        reviewer.security(candidate, CHECKER, dict(pip=['PyYAML==6.0', 'python_dateutil', 'ghost-package'], npm=['vue']))
        run = next(c for c in calls if c[0] == 'run')
        self.assertIn(CHECKER, run)
        flag = run.index('--model-authored')
        self.assertEqual(run[flag + 1], 'dateutil,yaml')                         # resolved through the installed distributions
        self.assertEqual(run[run.index('--unverified') + 1], 'ghost-package')    # a dependency that could not be resolved is flagged
        self.assertEqual(run[run.index('/checks/security.py') - 1], 'python')

    def test_without_a_checker_image_the_fixed_stack_scan_is_unchanged(self):
        calls = []
        temp = Path(self.enterContext(tempfile.TemporaryDirectory()))

        class Engine(FakeEngine):
            root = temp

            def runtime(self):
                return 'sha256:' + 'd' * 64

            def docker(self, *args, timeout=120):
                calls.append([str(a) for a in args])
                if args[0] == 'run':
                    return json.dumps(dict(checks=dict(static=True, secrets=True), findings=[]))
                if args[0] == 'inspect':
                    return json.dumps([dict(HostConfig=dict(ReadonlyRootfs=True, Privileged=False, NetworkMode='none', CapDrop=['ALL']),
                                            Config=dict(User='65534:65534'), Mounts=[dict(Destination='/checks', RW=False), dict(Destination='/candidate', RW=False)])])
                return ''
        Reviewer(Engine(lambda *a: {})).security(dict(path=str(temp), image_digest=IMAGE))
        run = next(c for c in calls if c[0] == 'run')
        self.assertNotIn('--model-authored', run)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, code, body, headers=()):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        for key, value in headers:
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == '/big':
            return self.respond(200, b'x' * 20000)
        if self.path == '/redirect':
            return self.respond(302, b'', [('Location', '/health')])
        if self.path == '/text':
            return self.respond(200, b'plain words')
        self.respond(200 if self.path == '/health' else 404, {'path': self.path})

    def do_POST(self):
        size = int(self.headers.get('Content-Length', 0))
        self.respond(201, {'echo': json.loads(self.rfile.read(size) or b'null')})


class ProbeScript(unittest.TestCase):
    def setUp(self):
        self.server = HTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def probe(self, *args, base=None):
        done = subprocess.run([sys.executable, str(ROOT / 'infra/checks/http_probe.py'), base or self.base, *args], capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def test_status_and_json_body(self):
        self.assertEqual(self.probe('GET', '/health'), dict(status=200, body={'path': '/health'}))
        self.assertEqual(self.probe('GET', '/nope')['status'], 404)

    def test_a_json_request_body_is_sent(self):
        self.assertEqual(self.probe('POST', '/items', json.dumps({'title': 'x'})), dict(status=201, body={'echo': {'title': 'x'}}))

    def test_redirects_are_not_followed_and_long_or_plain_bodies_are_bounded(self):
        self.assertEqual(self.probe('GET', '/redirect')['status'], 302)
        big = self.probe('GET', '/big')
        self.assertEqual(big['status'], 200)
        self.assertLessEqual(len(json.dumps(big['body'])), 5000)
        self.assertEqual(self.probe('GET', '/text')['body'], {'_text': 'plain words'})

    def test_a_connection_failure_is_reported_as_an_error_field_with_exit_code_zero(self):
        result = self.probe('GET', '/', base='http://127.0.0.1:9')
        self.assertIn('error', result)
        self.assertNotIn('status', result)

    def test_only_http_methods_and_rooted_paths_are_accepted(self):
        self.assertIn('error', self.probe('TRACE', '/'))
        self.assertIn('error', self.probe('GET', 'health'))


class SecurityModeForModelCandidates(unittest.TestCase):
    def scan(self, files, allowed=None):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        for name, text in files.items():
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text(text)
        args = [sys.executable, str(ROOT / 'infra/checks/security.py')] + (['--model-authored', allowed] if allowed is not None else [])
        done = subprocess.run(args, capture_output=True, text=True, timeout=30, env={'CANDIDATE_ROOT': str(root), 'PATH': '/usr/bin:/bin'})
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def test_the_fixed_stack_allow_list_is_unchanged_without_the_flag(self):
        result = self.scan({'app.py': 'import unittest\n'})
        self.assertTrue(any(f['rule'] == 'unsupported_import' for f in result['findings']))

    def test_model_mode_allows_stdlib_approved_dependencies_and_local_modules_only(self):
        files = {'main.py': 'import os\nimport requests\nimport helper\nfrom pkg import thing\n', 'helper.py': 'x = 1\n', 'pkg/__init__.py': '', 'pkg/thing.py': 'y = 2\n'}
        self.assertEqual(self.scan(files, 'requests')['findings'], [])
        undeclared = self.scan(dict(files, **{'extra.py': 'import numpy\n'}), 'requests')
        self.assertEqual([(f['path'], f['rule']) for f in undeclared['findings']], [('extra.py', 'unsupported_import')])

    def test_model_mode_keeps_every_other_rule(self):
        result = self.scan({'a.py': 'import os\nexec("x")\n', 'k.txt': 'AKIA' + 'A' * 16}, '')
        self.assertEqual(sorted(f['rule'] for f in result['findings']), ['dynamic_execution', 'secret_format'])
        self.assertFalse(result['checks']['static'])
        self.assertFalse(result['checks']['secrets'])


if __name__ == '__main__':
    unittest.main()
