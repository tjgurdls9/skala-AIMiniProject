"""Independent-review findings H-1 (check id collisions), H-2 (static scan skipping vendor/) and M-3 (secret pattern boundary)."""
import asyncio
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from backend.contracts import ROOT, SECRET
from runner.check_runner import CheckOutcome, acceptance_verdicts
import test_plan_extras as extras
import test_runtime as fixtures


class KoreanCriteria(fixtures.FakeModel):
    """A planner whose criterion ids are not ASCII, which the schema allows."""
    async def generate(self, packet, schema):
        return dict(fixtures.PLAN, acceptance=[dict(id='검색', title='검색', description='검색이 된다'),
                                               dict(id='추천', title='추천', description='추천이 된다'),
                                               dict(id='AC 1', title='하나', description='하나'), dict(id='AC_1', title='둘', description='둘'),
                                               dict(id='x' * 40 + 'a', title='긴1', description='긴1'), dict(id='x' * 40 + 'b', title='긴2', description='긴2')])


class CheckIds(unittest.TestCase):
    setUp = extras.PlanExtrasChecks.setUp
    command = extras.PlanExtrasChecks.command
    post_command = extras.PlanExtrasChecks.post_command
    start = extras.PlanExtrasChecks.start
    spec = extras.PlanExtrasChecks.spec

    def test_every_check_of_a_plan_has_its_own_id_whatever_the_criterion_ids_look_like(self):
        run_id = self.start(KoreanCriteria())
        asyncio.run(self.worker.tick())
        _, plan = self.spec(run_id)
        ids = [c['id'] for c in plan['verification']]
        self.assertEqual(len(ids), 6)
        self.assertEqual(len(set(ids)), 6, ids)

    def test_ordinary_criterion_ids_keep_the_readable_check_ids(self):
        run_id = self.start(extras.Scripted())
        asyncio.run(self.worker.tick())
        _, plan = self.spec(run_id)
        self.assertEqual([c['id'] for c in plan['verification']], ['AC1-1', 'AC2-1'])

    def test_a_repeated_check_id_never_lets_a_failed_check_count_for_another_criterion(self):
        acceptance = [dict(id='A', title='a', description='a'), dict(id='B', title='b', description='b')]
        verification = [dict(id='dup', ac_ids=['A'], kind='http', steps=[]), dict(id='dup', ac_ids=['B'], kind='http', steps=[])]
        outcomes = [CheckOutcome('dup', 'failed', '', {}), CheckOutcome('dup', 'passed', '', {})]
        statuses = {v['id']: v['status'] for v in acceptance_verdicts(acceptance, verification, [], outcomes)}
        self.assertEqual(statuses, {'A': 'unmet', 'B': 'unmet'})
        from runner.review import model_validation_body
        spec = dict(acceptance=acceptance, verification=verification, manual_acceptance=[])
        self.assertEqual(model_validation_body(spec, outcomes, dict(healthy=True))['verdict'], 'fail')


class StaticScan(unittest.TestCase):
    def scan(self, files):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        for name, text in files.items():
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text(text)
        done = subprocess.run([sys.executable, str(ROOT / 'infra/checks/security.py'), '--model-authored', ''], capture_output=True, text=True,
                              env={'CANDIDATE_ROOT': str(root), 'PATH': ''})
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def test_code_under_a_directory_named_vendor_is_scanned_like_any_other(self):
        result = self.scan({'server/vendor/helper.py': 'import os\nos.system("id")\neval("1")\n', 'server/main.py': 'import vendor.helper\n'})
        self.assertFalse(result['checks']['static'])
        self.assertIn('server/vendor/helper.py', {f['path'] for f in result['findings']})

    def test_a_secret_under_vendor_is_found(self):
        result = self.scan({'vendor/key.txt': 'AKIA' + 'A' * 16})
        self.assertFalse(result['checks']['secrets'])


class StaticScanSecretBoundary(unittest.TestCase):
    scan = StaticScan.scan
    """Re-review N-1: the scan's own secret pattern needs the same word boundary as the write-time check."""
    def test_ordinary_kebab_case_names_are_not_secrets_in_the_scan(self):
        result = self.scan({'web/style.css': '.task-description-container { color: red }\n',
                            'web/index.html': '<div class="disk-usage-monitoring-report"></div>\n'})
        self.assertTrue(result['checks']['secrets'], result)

    def test_a_real_key_next_to_punctuation_is_still_found_in_the_scan(self):
        result = self.scan({'server/config.py': 'API_KEY = "sk-' + 'a' * 24 + '"\n'})
        self.assertFalse(result['checks']['secrets'])


class SecretPattern(unittest.TestCase):
    def test_words_that_merely_end_in_sk_are_not_secrets(self):
        for text in ('risk-assessment-calculation.py', 'task-management-service-handler', 'disk-usage-monitoring-report', 'a_disk-usage-monitoring-report'):
            self.assertIsNone(SECRET.search(text), text)

    def test_real_key_formats_are_still_found(self):
        for text in ('sk-' + 'a' * 24, 'key=sk-' + 'A1_' * 8, ' "sk-' + 'b' * 30 + '"', 'AKIA' + 'B' * 16, 'ghp_' + 'c' * 24):
            self.assertIsNotNone(SECRET.search(text), text)


if __name__ == '__main__':
    unittest.main()
