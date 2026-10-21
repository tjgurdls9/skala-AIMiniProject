"""The protected security reviewer and scanner preparation, with Docker replaced by a scripted engine."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from runner.model import ModelUnavailable
from runner.review import Reviewer, scan_covered
from runner.sandbox import Sandbox
import test_model_review as review

IMAGE_TAR_FLAG = '--output'
SCANNER = dict(image_id='sha256:' + 'e' * 64, version='0.121.0')


def grype_report(severity='low', providers=('alpine', 'github'), valid=True):
    return dict(descriptor=dict(name='grype', version='0.121.0', db=dict(status=dict(valid=valid), providers={p: {} for p in providers})),
                source=dict(type='image'), distro=dict(name='alpine'),
                matches=[dict(vulnerability=dict(severity=severity))])


class ScriptedEngine:
    """Answers each docker subcommand the security reviewer issues; `checks` is what the in-container static checker prints."""
    limits = staticmethod(Sandbox.limits)

    def __init__(self, root, checks=None, report=None, isolated=True):
        self.root, self.calls, self.cleaned = root, [], []
        self.checks, self.report, self.isolated = checks or dict(static=True, secrets=True), report or grype_report(), isolated

    def docker(self, *args, timeout=120):
        self.calls.append([str(a) for a in args])
        if args[0] == 'save':
            Path(args[args.index(IMAGE_TAR_FLAG) + 1]).write_bytes(b'tar')
            return ''
        if args[0] == 'inspect':
            host = dict(ReadonlyRootfs=True, Privileged=False, NetworkMode='none' if self.isolated else 'bridge', CapDrop=['ALL'])
            return json.dumps([dict(HostConfig=host, Config=dict(User='65534:65534'), Mounts=[dict(Destination='/checks', RW=False), dict(Destination='/candidate', RW=False)])])
        if '/checks/security.py' in args:
            return json.dumps(dict(checks=dict(self.checks), findings=[]))
        if 'docker-archive:/scan/candidate.tar' in args:
            return json.dumps(self.report)
        if args[:2] == ('image', 'inspect'):
            return SCANNER['image_id'] + '\n'
        if 'status' in args:
            return json.dumps(dict(valid=True))
        return ''

    def cleanup(self, name):
        self.cleaned.append(name)
        return True


class SecurityReview(unittest.TestCase):
    def setUp(self):
        self.temp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (self.temp / 'cand').mkdir()
        self.candidate = dict(path=str(self.temp / 'cand'), image_digest=review.IMAGE, commit_sha='c' * 40,
                              dependency_modules={'fastapi': ['fastapi', 'starlette']})

    def reviewer(self, **engine):
        self.engine = ScriptedEngine(self.temp, **engine)
        return Reviewer(self.engine)

    def prepared(self):
        (self.temp / 'scanner.json').write_text(json.dumps(SCANNER))

    def test_without_a_prepared_scanner_the_review_is_not_run(self):
        result = self.reviewer().security(self.candidate, review.CHECKER)
        self.assertEqual(result['verdict'], 'not_run')
        self.assertTrue(result['checks']['isolation'])
        self.assertEqual(len(self.engine.cleaned), 1)

    def test_a_clean_scan_of_the_exact_image_passes(self):
        self.prepared()
        result = self.reviewer().security(self.candidate, review.CHECKER)
        self.assertEqual(result['verdict'], 'pass')
        self.assertEqual(result['scanner'], SCANNER)
        scan = next(c for c in self.engine.calls if 'docker-archive:/scan/candidate.tar' in c)
        self.assertEqual(scan[scan.index('--network') + 1], 'none')                                  # the scanner has no network either
        self.assertIn('GRYPE_DB_AUTO_UPDATE=false', scan)

    def test_a_high_severity_match_fails_the_review(self):
        self.prepared()
        result = self.reviewer(report=grype_report('High')).security(self.candidate, review.CHECKER)
        self.assertEqual((result['verdict'], result['checks']['dependency_image']), ('fail', False))

    def test_a_scan_that_did_not_cover_the_image_cannot_pass(self):
        self.prepared()
        result = self.reviewer(report=grype_report(providers=('alpine',))).security(self.candidate, review.CHECKER)
        self.assertEqual((result['verdict'], result['checks']['scanner_coverage']), ('fail', False))

    def test_a_failed_static_check_or_a_leaky_container_fails_the_review(self):
        self.prepared()
        self.assertEqual(self.reviewer(checks=dict(static=False, secrets=True)).security(self.candidate, review.CHECKER)['verdict'], 'fail')
        leaky = self.reviewer(isolated=False).security(self.candidate, review.CHECKER)
        self.assertEqual((leaky['verdict'], leaky['checks']['isolation']), ('fail', False))

    def test_approved_dependencies_are_resolved_to_import_names_and_unknown_ones_are_flagged(self):
        reviewer = self.reviewer()
        reviewer.security(self.candidate, review.CHECKER, dict(pip=['FastAPI==0.1', 'left_pad'], npm=[]))
        command = next(c for c in self.engine.calls if '/checks/security.py' in c)
        self.assertEqual(command[command.index('--model-authored') + 1], 'fastapi,starlette')
        self.assertEqual(command[command.index('--unverified') + 1], 'left-pad')

    def test_a_superseded_attempt_stops_before_anything_runs_and_still_cleans_up(self):
        reviewer = Reviewer(ScriptedEngine(self.temp), current=lambda: False)
        with self.assertRaises(ModelUnavailable):
            reviewer.security(self.candidate, review.CHECKER)
        self.assertEqual(len(reviewer.engine.cleaned), 1)
        self.assertEqual(reviewer.engine.calls, [])

    def test_scan_coverage_needs_a_valid_database_and_the_scanner_version(self):
        self.assertTrue(scan_covered(grype_report(), SCANNER))
        self.assertFalse(scan_covered(grype_report(valid=False), SCANNER))
        self.assertFalse(scan_covered(grype_report(), dict(SCANNER, version='9.9.9')))
        self.assertFalse(scan_covered(grype_report('unknown'), SCANNER))

    def test_preparing_the_scanner_records_the_image_and_database_status(self):
        reviewer = self.reviewer()
        (self.temp / 'grype-db').mkdir(exist_ok=True)
        result = reviewer.prepare_scanner()
        self.assertEqual((result['image_id'], result['database']), (SCANNER['image_id'], dict(valid=True)))
        self.assertEqual(json.loads((self.temp / 'scanner.json').read_text())['version'], '0.121.0')


class CandidateCommandTimeouts(unittest.TestCase):
    def test_a_command_check_that_times_out_is_reported_and_its_container_removed(self):
        def slow(args, **kwargs):
            raise subprocess.TimeoutExpired(args, kwargs['timeout'])
        engine = review.FakeEngine(lambda m, p, b: dict(status=200, body={}))
        reviewer = Reviewer(engine, runner=slow, sleep=lambda s: None)
        candidate = dict(path='/nonexistent', image_digest=review.IMAGE, commit_sha='c' * 40,
                         app=dict(runtime='python', start=['python', 'app.py'], port=8080, health='/health'))
        specs = [dict(id='c1', ac_ids=['AC1'], kind='command', argv=['python', '-c', 'pass'], expect=dict(exit=0))]
        outcomes, _ = reviewer.model_validation(candidate, specs, review.CHECKER)
        self.assertEqual(outcomes[0].status, 'failed')
        self.assertTrue(engine.cleaned)


if __name__ == '__main__':
    unittest.main()
