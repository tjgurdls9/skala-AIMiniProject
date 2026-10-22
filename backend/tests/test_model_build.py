"""F3: an approved model-authored plan is built by the model loop through the worker, with the server judging RED/GREEN."""
import asyncio
import copy
import json
import unittest
from pathlib import Path

from backend.contracts import canonical
from runner.commands import CommandResult
import test_plan_extras as extras
import test_runtime as fixtures

SCRIPTS = dict(
    contract=[('write_file', dict(path='contract/api.json', content='{}')), ('finish', None)],
    backend=[('write_file', dict(path='server/test_main.py', content='t')), ('run_tests', dict(argv=['python', '-m', 'pytest'])),
             ('write_file', dict(path='server/main.py', content='c')), ('run_tests', dict(argv=['python', '-m', 'pytest'])), ('finish', None)],
    frontend=[('write_file', dict(path='web/app.test.js', content='t')), ('run_tests', dict(argv=['node', '--test'])),
              ('write_file', dict(path='web/app.js', content='c')), ('run_tests', dict(argv=['node', '--test'])), ('finish', None)],
    integration=[('write_file', dict(path='lifecycle.app.json', content=json.dumps(dict(runtime='python', start=['python', '-m', 'http.server', '8080'], port=8080, health='/')))),
                 ('write_file', dict(path='integration/flow.py', content='c')), ('run_tests', dict(argv=['python', '-m', 'pytest'])), ('finish', None)])


class BuildScripted(extras.Scripted):
    """Plans like Scripted; as the builder it replays SCRIPTS by how many ledger steps the task already has."""
    async def generate(self, packet, schema):
        if packet.get('step') != 'act':
            return await super().generate(packet, schema)
        self.calls.append(packet)
        tool, args = SCRIPTS[packet['task']['kind']][len(packet['history'])]
        return dict(tool=tool, **({'args': args} if args is not None else {'summary': '완료'}))


class FakeExecutor:
    """Exit codes in the order the tasks run their tests: backend RED/GREEN, frontend RED/GREEN, integration GREEN."""
    images = dict(python='python@sha256:' + 'a' * 64, node='node@sha256:' + 'b' * 64)

    def __init__(self, codes):
        self.codes, self.calls = list(codes), []

    def run(self, workspace, argv, cwd, timeout, **kwargs):
        self.calls.append(argv)
        code = self.codes.pop(0)
        return CommandResult(code, 'out', 'Ran 1 test in 0.0s\n\nOK' if code == 0 else '', False, False)


class ModelBuildChecks(unittest.TestCase):
    setUp = fixtures.RuntimeChecks.setUp
    command = fixtures.RuntimeChecks.command
    post_command = fixtures.RuntimeChecks.post_command

    def approved_run(self, model, codes=(1, 0, 1, 0, 0)):
        self.worker.model = model
        self.worker.heartbeat()
        project = self.store.project(dict(title='generic', request='generic request'))
        run_id = self.store.create_run(project['project_id'], dict(mode='live'), template_id='blank-v1')['run_id']
        asyncio.run(self.worker.tick())
        snapshot = self.store.snapshot(run_id)
        approval = snapshot['approvals'][-1]
        response = self.post_command(self.command(snapshot, 'decide', dict(approval_id=approval['id'], target_digest=approval['target_digest'], decision='approve')))
        self.assertEqual(response.status_code, 202, response.text)
        self.executor = FakeExecutor(codes)
        self.worker.pipeline.executor = self.executor
        self.builds = []

        def docker(*args, timeout=120):                # the offline image build is the only docker call a model-authored freeze makes
            self.builds.append([str(a) for a in args])
            if args[0] == 'build':
                Path(args[args.index('--iidfile') + 1]).write_text('sha256:' + 'b' * 64)
            return ''
        self.worker.pipeline.engine.docker = docker
        return run_id

    def drain(self, run_id, limit=30):
        for _ in range(limit):
            if not asyncio.run(self.worker.tick()) or self.store.snapshot(run_id)['state'] == 'reviewing':
                break              # reviews need real containers; this file stops once the candidate is frozen
        return self.store.snapshot(run_id)

    def test_every_task_is_built_by_the_model_in_dependency_order_and_freezes_a_candidate(self):
        model = BuildScripted()
        run_id = self.approved_run(model)
        snapshot = self.drain(run_id)
        builders = [t for t in snapshot['tasks'] if t['role'] == 'builder']
        self.assertEqual([t['state'] for t in builders], ['succeeded'] * 4)
        self.assertEqual(snapshot['state'], 'reviewing')
        calls = self.store.tool_calls(run_id)
        by_task = {}
        for call in calls:
            by_task.setdefault(call['task_id'], []).append((call['tool'], call['exit_code']))
        titles = {t['id']: t['title'] for t in builders}
        self.assertEqual({titles[k]: v for k, v in by_task.items()}, {
            '계약': [('write_file', None)],
            '서버': [('write_file', None), ('run_tests', 1), ('write_file', None), ('run_tests', 0)],
            '화면': [('write_file', None), ('run_tests', 1), ('write_file', None), ('run_tests', 0)],
            '통합': [('write_file', None), ('write_file', None), ('run_tests', 0)]})
        order = [titles[c['task_id']] for c in calls if c['tool'] == 'write_file']
        self.assertLess(order.index('계약'), order.index('서버'))
        self.assertLess(max(i for i, t in enumerate(order) if t in ('서버', '화면')), order.index('통합'))
        self.assertEqual(len([b for b in self.builds if b[0] == 'build']), 1)

    def test_the_diff_artifact_lists_the_files_the_model_created(self):
        run_id = self.approved_run(BuildScripted())
        snapshot = self.drain(run_id)
        diffs = [self.store.read_artifact(a['id']) for a in snapshot['artifacts'] if a['kind'] == 'code_diff']
        changed = sorted(c['path'] for d in diffs for c in d['changes'])
        self.assertEqual(changed, ['contract/api.json', 'integration/flow.py', 'lifecycle.app.json', 'server/main.py', 'server/test_main.py', 'web/app.js', 'web/app.test.js'])
        self.assertTrue(all(c['diff'].startswith('---') for d in diffs for c in d['changes']))

    def test_writes_outside_the_task_scope_are_refused_and_recorded(self):
        class Wanderer(BuildScripted):
            async def generate(self, packet, schema):
                if packet.get('step') == 'act' and packet['task']['kind'] == 'contract' and not packet['history']:
                    self.calls.append(packet)
                    return dict(tool='write_file', args=dict(path='server/stolen.py', content='x'))
                return await super().generate(packet, schema)
        run_id = self.approved_run(Wanderer())
        snapshot = self.drain(run_id)
        refused = [c for c in self.store.tool_calls(run_id) if not c['ok']]
        self.assertTrue(refused and refused[0]['error_code'] == 'FORBIDDEN')
        self.assertNotEqual(snapshot['state'], 'reviewing')           # the scripted model then stalls on a repeated refusal
        self.assertNotIn(Path('server/stolen.py').as_posix(), canonical(snapshot['artifacts']))

    def test_a_model_that_never_gets_a_failing_test_cannot_write_implementation(self):
        # tests pass at once (exit 0) so RED never happens; the server keeps the implementation locked and the run stops for the user
        run_id = self.approved_run(BuildScripted(), codes=[0] * 10)
        snapshot = self.drain(run_id)
        self.assertEqual(snapshot['state'], 'needs_input')
        calls = [c for c in self.store.tool_calls(run_id) if c['tool'] == 'write_file' and c['args']['path'] == 'server/main.py']
        self.assertTrue(calls and not any(c['ok'] for c in calls))
        self.assertFalse((Path(self.temp.name) / 'workspaces').exists() and any(Path(self.temp.name).rglob('server/main.py')))


    def test_a_changed_tool_policy_makes_an_unapproved_plan_stale_and_blocks_an_approved_one(self):
        import runner.commands as commands
        self.worker.model = BuildScripted()
        self.worker.heartbeat()
        project = self.store.project(dict(title='generic', request='generic request'))
        run_id = self.store.create_run(project['project_id'], dict(mode='live'), template_id='blank-v1')['run_id']
        asyncio.run(self.worker.tick())
        snapshot = self.store.snapshot(run_id)
        approval = snapshot['approvals'][-1]
        original = commands.TOOL_POLICY['timeout_max']
        commands.TOOL_POLICY['timeout_max'] = original - 1
        self.addCleanup(commands.TOOL_POLICY.__setitem__, 'timeout_max', original)
        response = self.post_command(self.command(snapshot, 'decide', dict(approval_id=approval['id'], target_digest=approval['target_digest'], decision='approve')))
        self.assertEqual(response.status_code, 409)
        self.assertIn('STALE_APPROVAL', response.text)

    def test_policy_changed_after_approval_stops_the_builder_for_a_new_approval(self):
        import runner.commands as commands
        run_id = self.approved_run(BuildScripted())
        original = commands.TOOL_POLICY['timeout_max']
        commands.TOOL_POLICY['timeout_max'] = original - 1
        self.addCleanup(commands.TOOL_POLICY.__setitem__, 'timeout_max', original)
        snapshot = self.drain(run_id)
        self.assertEqual(snapshot['state'], 'needs_input')
        self.assertEqual(self.store.tool_calls(run_id), [])           # nothing ran under the changed policy

    def test_the_approved_dependency_range_reaches_the_builder_and_nothing_else_may_be_installed(self):
        class Installer(BuildScripted):
            async def generate(self, packet, schema):
                if packet.get('step') == 'act' and packet['task']['kind'] == 'contract':
                    self.calls.append(packet)
                    return dict(tool='install_dependencies', args=dict(manager='pip', packages=['requests']))
                return await super().generate(packet, schema)
        run_id = self.approved_run(Installer())
        snapshot = self.drain(run_id)
        self.assertEqual(snapshot['state'], 'needs_input')
        self.assertIn('의존성', snapshot['reason'])
        entry = self.store.tool_calls(run_id)[0]
        self.assertEqual((entry['tool'], entry['ok'], entry['error_code']), ('install_dependencies', False, 'FORBIDDEN'))
        self.assertEqual(self.executor.calls, [])


    def test_claimed_builder_jobs_carry_exactly_the_approved_dependency_names(self):
        self.approved_run(BuildScripted())
        job = self.worker.claim()
        self.assertEqual(job['packet']['options']['allowed_dependencies'], {'pip': ['fastapi'], 'npm': []})


    def test_each_task_is_one_commit_and_the_candidate_is_the_last_commit(self):
        import subprocess
        from runner.candidate import git_dir_of
        run_id = self.approved_run(BuildScripted())
        snapshot = self.drain(run_id)
        workspace = next(p for p in (Path(self.temp.name) / 'workspaces' / run_id).iterdir() if not p.name.endswith(('.git', '.deps')))
        history = subprocess.run(['git', '--git-dir', str(git_dir_of(workspace)), 'log', '--format=%H|%s'], capture_output=True, text=True).stdout.splitlines()
        self.assertEqual(len(history), 4)
        self.assertEqual([h.split('|', 1)[1].split(' [')[0] for h in reversed(history)], ['task: 계약', 'task: 서버', 'task: 화면', 'task: 통합'])
        with self.store.transaction() as db:
            candidate = json.loads(db.execute('SELECT body FROM candidates WHERE run_id=?', (run_id,)).fetchone()[0])
        self.assertEqual(candidate['commit_sha'], history[0].split('|')[0])
        self.assertEqual(candidate['app']['health'], '/')
        diffs = [self.store.read_artifact(a['id']) for a in snapshot['artifacts'] if a['kind'] == 'code_diff']
        self.assertEqual(sorted(d['commit'] for d in diffs), sorted(h.split('|')[0] for h in history))

    def test_a_green_builder_never_marks_any_criterion_met_and_waits_for_independent_review(self):
        run_id = self.approved_run(BuildScripted())
        snapshot = self.drain(run_id)
        self.assertEqual(snapshot['state'], 'reviewing')
        statuses = {item['status'] for item in self.store.acceptance_status(run_id)['items']}
        self.assertEqual(statuses, {'unmet'})                                   # only a validator report can say `met`
        self.assertEqual(snapshot['reports'], [])
        roles = sorted(t['role'] for t in snapshot['tasks'] if t['state'] in ('ready', 'pending') and t['role'] in ('validator', 'security'))
        self.assertEqual(roles, ['security', 'validator'])


    def finish_reviews(self, run_id, outcomes, security='pass'):
        from unittest import mock
        from runner.check_runner import CheckOutcome
        from runner.review import Reviewer
        with self.store.transaction() as db:
            spec = json.loads(db.execute('SELECT package FROM specs WHERE run_id=?', (run_id,)).fetchone()[0])
        results = [CheckOutcome(c['id'], outcomes.get(c['id'], 'passed'), '', {}) for c in spec['verification']]
        secure = dict(verdict=security, checks=dict(static=security == 'pass'), tools_note='faked')
        with mock.patch.object(Reviewer, 'model_validation', lambda self, candidate, specs, image: (results, dict(healthy=True))), \
                mock.patch.object(Reviewer, 'security', lambda self, candidate, image=None, deps=None: dict(secure)):
            for _ in range(4):
                if not asyncio.run(self.worker.tick()) or self.store.snapshot(run_id)['state'] == 'preview_ready':
                    break              # the release job needs real containers; stop where the preview becomes possible
        return self.store.snapshot(run_id)

    def test_validator_and_security_review_a_model_candidate_and_only_passing_checks_open_the_preview(self):
        run_id = self.approved_run(BuildScripted())
        self.assertEqual(self.drain(run_id)['state'], 'reviewing')
        snapshot = self.finish_reviews(run_id, {})
        self.assertEqual(snapshot['state'], 'preview_ready')
        self.assertEqual({r['role']: r['verdict'] for r in snapshot['reports']}, {'validator': 'pass', 'security': 'pass'})
        self.assertEqual({i['status'] for i in self.store.acceptance_status(run_id)['items']}, {'met'})

    def test_a_formally_green_builder_whose_implementation_fails_the_approved_check_does_not_pass_review(self):
        run_id = self.approved_run(BuildScripted())
        self.drain(run_id)
        with self.store.transaction() as db:
            check = json.loads(db.execute('SELECT package FROM specs WHERE run_id=?', (run_id,)).fetchone()[0])['verification'][0]
        snapshot = self.finish_reviews(run_id, {check['id']: 'failed'})
        self.assertNotEqual(snapshot['state'], 'preview_ready')
        self.assertEqual({r['role']: r['verdict'] for r in snapshot['reports']}, {'validator': 'fail', 'security': 'pass'})
        statuses = {i['id']: i['status'] for i in self.store.acceptance_status(run_id)['items']}
        self.assertEqual(sorted(statuses.values()), ['met', 'unmet'])                    # the criterion the check covers stays unmet
        self.assertFalse([t for t in snapshot['tasks'] if t['role'] == 'release' and t['state'] == 'ready'])

    def test_a_failed_security_review_blocks_even_when_every_check_passes(self):
        run_id = self.approved_run(BuildScripted())
        self.drain(run_id)
        snapshot = self.finish_reviews(run_id, {}, security='fail')
        self.assertNotEqual(snapshot['state'], 'preview_ready')


if __name__ == '__main__':
    unittest.main()
