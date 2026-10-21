"""F3: the model-driven builder loop. A scripted fake model chooses actions; the server executes, records and judges."""
import asyncio
import copy
import tempfile
import unittest
from pathlib import Path

from backend.contracts import DomainError, canonical, digest
from backend.store import Store
from runner.commands import CommandResult
from runner.context import BUDGET
from runner.builder_loop import ACTION_SCHEMA, INSTRUCTIONS, BuilderLoop, action_schema
from runner.tools import ToolBox
from runner.workspace import Workspace
from test_tools import RecordingExecutor

SPEC = dict(spec_version_id='s' * 32, goal='목표', features=['기능'], non_goals=[], constraints=['무료만'],
            acceptance=[dict(id='AC1', title='첫째', description='첫째 조건'), dict(id='AC2', title='둘째', description='둘째 조건')],
            verification=[dict(id='AC1-1', ac_ids=['AC1'], kind='http', steps=[dict(method='GET', path='/health', expect=dict(status=200))]),
                          dict(id='AC2-1', ac_ids=['AC2'], kind='command', argv=['python', '-m', 'pytest'], expect=dict(exit=0))],
            dependencies=dict(pip=['fastapi'], npm=[]))


class Script:
    """Replays a fixed list of actions (dicts); records every packet it was shown."""
    def __init__(self, actions):
        self.actions, self.packets, self.schemas = list(actions), [], []

    async def infer(self, job, call, schema):
        self.packets.append(copy.deepcopy(call))
        self.schemas.append(copy.deepcopy(schema))
        item = self.actions.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def act(tool, **args):
    return dict(tool=tool, args=args)


FINISH = dict(tool='finish', summary='끝')


class LoopChecks(unittest.TestCase):
    def setUp(self):
        self.temp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.store = Store(self.temp / 'state.sqlite3')
        project = self.store.project(dict(title='synthetic', request='generic request'))
        self.run_id = self.store.create_run(project['project_id'], dict(mode='live'))['run_id']
        (self.temp / 'ws').mkdir()
        self.executor = RecordingExecutor()
        self.codes = []

        def run(workspace, argv, cwd, timeout, **kwargs):
            code = self.codes.pop(0) if self.codes else 0
            return CommandResult(code, 'out', 'err', False, False)
        self.executor.run = run

    def toolbox(self, kind='backend'):
        who = dict(role='builder', run_id=self.run_id, job_id='j', attempt_id='a', task_id='t1', task_kind=kind)
        return ToolBox(lambda: who, self.store, Workspace(self.temp / 'ws'), self.executor, deps_dir=self.temp / 'deps')

    def job(self, kind='backend'):
        return dict(run_id=self.run_id, id='j', packet=dict(
            latest_spec=SPEC, prior_draft=None, mandatory_policy='policy', unresolved_failures=[],
            options=dict(task_id='t1', task_kind=kind, task_title='서버', acceptance_ids=['AC1'], write_scope=['server/**', 'tests/**'])))

    def run_loop(self, actions, kind='backend', toolbox=None):
        script = Script(actions)
        result = asyncio.run(BuilderLoop(self.store).run(self.job(kind), script, toolbox or self.toolbox(kind)))
        return result, script

    def test_a_full_tdd_cycle_is_executed_recorded_and_accepted_by_the_server(self):
        self.codes = [1, 0]
        result, script = self.run_loop([
            act('write_file', path='tests/test_a.py', content='t'), act('run_tests', argv=['python', '-m', 'pytest']),
            act('write_file', path='server/main.py', content='c'), act('run_tests', argv=['python', '-m', 'pytest']), FINISH])
        self.assertEqual(result['summary'], '끝')
        entries = self.store.tool_calls(self.run_id, 't1')
        self.assertEqual([(e['tool'], e['exit_code']) for e in entries],
                         [('write_file', None), ('run_tests', 1), ('write_file', None), ('run_tests', 0)])
        self.assertEqual([p['gate']['phase'] for p in script.packets], ['red', 'red', 'impl', 'impl', 'done'])

    def test_finishing_early_is_refused_and_the_reason_goes_back_to_the_model(self):
        self.codes = [1, 0]
        result, script = self.run_loop([
            FINISH, act('write_file', path='tests/test_a.py', content='t'), act('run_tests', argv=['python', '-m', 'pytest']),
            act('write_file', path='server/main.py', content='c'), act('run_tests', argv=['python', '-m', 'pytest']), FINISH])
        self.assertEqual(len(script.packets), 6)
        self.assertFalse(script.packets[1]['last_observation']['ok'])
        self.assertIn('변경', script.packets[1]['last_observation']['error'])

    def test_a_denied_or_malformed_action_is_an_observation_not_a_crash(self):
        self.codes = [1, 0]
        result, script = self.run_loop([
            act('write_file', path='server/main.py', content='too early'),             # RED gate refuses
            dict(tool='format_disk', args={}),                                          # not a tool
            act('read_file', path='../escape'),                                         # path policy
            act('write_file', path='tests/test_a.py', content='t'), act('run_tests', argv=['python', '-m', 'pytest']),
            act('write_file', path='server/main.py', content='c'), act('run_tests', argv=['python', '-m', 'pytest']), FINISH])
        self.assertEqual(result['summary'], '끝')
        errors = [p['last_observation'] for p in script.packets[1:4]]
        self.assertTrue(all(not o['ok'] for o in errors))
        self.assertIn('FORBIDDEN', errors[0]['error'])
        self.assertIn('형식', errors[1]['error'])

    def test_the_same_action_with_the_same_outcome_three_times_stops_for_the_user(self):
        with self.assertRaises(DomainError) as caught:
            self.run_loop([act('read_file', path='missing.txt')] * 5)
        self.assertEqual(caught.exception.code, 'INVALID_COMMAND')
        self.assertIn('반복', caught.exception.message)

    def test_alternating_between_two_failing_actions_is_a_repetition_too(self):
        # the real model alternated finish / list_files for 40 calls; interleaving must not hide a loop
        refused = FINISH
        bad = act('list_files', path='.')                  # list_files takes no argument
        script = Script([refused, bad] * 20)
        with self.assertRaises(DomainError) as caught:
            asyncio.run(BuilderLoop(self.store).run(self.job(), script, self.toolbox()))
        self.assertIn('반복', caught.exception.message)
        self.assertLessEqual(len(script.packets), 6)

    def test_progress_resets_the_repetition_streak(self):
        self.codes = [1, 0]
        result, _ = self.run_loop([act('read_file', path='missing.txt')] * 2 + [
            act('write_file', path='tests/test_a.py', content='t'), act('read_file', path='missing.txt'),
            act('run_tests', argv=['python', '-m', 'pytest']), act('write_file', path='server/main.py', content='c'),
            act('run_tests', argv=['python', '-m', 'pytest']), FINISH])
        self.assertEqual(result['summary'], '끝')

    def test_every_packet_stays_within_the_budget_and_never_carries_other_roles_data(self):
        for index in range(80):
            (self.temp / 'ws' / f'file{index}.txt').write_text('x' * 50)
        self.codes = [1, 0]
        big = 'y' * 20000
        (self.temp / 'ws' / 'big.txt').write_text(big[:60000])
        result, script = self.run_loop([
            act('read_file', path='big.txt'), act('write_file', path='tests/test_a.py', content='t'),
            act('run_tests', argv=['python', '-m', 'pytest']), act('write_file', path='server/main.py', content='c'),
            act('run_tests', argv=['python', '-m', 'pytest']), FINISH])
        self.assertTrue(all(len(canonical(p).encode()) <= BUDGET for p in script.packets))
        allowed = {'role', 'step', 'mandatory_policy', 'approved_spec', 'prior_draft', 'unresolved_failures', 'task', 'acceptance', 'checks',
                   'dependencies', 'files', 'history', 'last_observation', 'gate', 'instructions'}
        self.assertTrue(all(set(p) <= allowed for p in script.packets))

    def test_only_this_tasks_acceptance_and_checks_are_shown(self):
        script = Script([act('write_file', path='tests/test_a.py', content='t')])
        with self.assertRaises(IndexError):          # the script ends after one action; only the first packet matters here
            asyncio.run(BuilderLoop(self.store).run(self.job(), script, self.toolbox()))
        first = script.packets[0]
        self.assertEqual([a['id'] for a in first['acceptance']], ['AC1'])
        self.assertEqual([c['id'] for c in first['checks']], ['AC1-1'])
        self.assertEqual(first['task']['kind'], 'backend')

    def test_history_is_rebuilt_from_the_ledger_after_a_restart(self):
        self.codes = [1]
        script = Script([act('write_file', path='tests/test_a.py', content='t'), act('run_tests', argv=['python', '-m', 'pytest'])])
        with self.assertRaises(IndexError):
            asyncio.run(BuilderLoop(self.store).run(self.job(), script, self.toolbox()))
        again = Script([act('read_file', path='other')])
        with self.assertRaises(IndexError):          # a fresh loop instance (a restarted worker) starts from the ledger
            asyncio.run(BuilderLoop(self.store).run(self.job(), again, self.toolbox()))
        history = again.packets[0]['history']
        self.assertTrue(any(h['tool'] == 'run_tests' and h['exit_code'] == 1 for h in history))
        self.assertEqual(again.packets[0]['gate']['phase'], 'impl')
        self.assertNotIn('content', canonical(history))

    def test_an_install_outside_the_approved_range_escalates_to_the_user(self):
        from runner.tools import EscalateToUser
        box = self.toolbox()
        box.allowed_dependencies = {'pip': {'fastapi'}}
        with self.assertRaises(EscalateToUser):
            self.run_loop([act('install_dependencies', manager='pip', packages=['requests'])], toolbox=box)

    def test_non_tdd_tasks_need_a_change_but_no_test_phase(self):
        result, script = self.run_loop([act('write_file', path='contract/api.json', content='{}'), FINISH], kind='contract')
        self.assertEqual(result['summary'], '끝')
        self.assertEqual(script.packets[0]['gate']['phase'], 'free')

    def test_undecodable_model_output_becomes_an_observation_and_is_ledgered(self):
        import json
        broken = json.JSONDecodeError('Unterminated string', '{"tool": "write_file", "args": {"path": "a.py", "content": "def f():\n', 40)
        self.codes = [1, 0]
        result, script = self.run_loop([
            broken, act('write_file', path='tests/test_a.py', content='t'), act('run_tests', argv=['python', '-m', 'pytest']),
            act('write_file', path='server/main.py', content='c'), act('run_tests', argv=['python', '-m', 'pytest']), FINISH])
        self.assertEqual(result['summary'], '끝')
        self.assertFalse(script.packets[1]['last_observation']['ok'])
        self.assertIn('JSON', script.packets[1]['last_observation']['error'])
        entry = next(e for e in self.store.tool_calls(self.run_id, 't1') if e['tool'] == 'model_output_error')
        self.assertEqual((entry['ok'], entry['error_code']), (False, 'MODEL_FORMAT'))
        self.assertIn('def f()', entry['args']['raw_head'])
        # a ledgered format error does not move the RED/GREEN state
        self.assertEqual(script.packets[1]['gate']['phase'], 'red')

    def test_repeated_undecodable_output_stops_for_the_user(self):
        import json
        broken = json.JSONDecodeError('Unterminated string', '{"tool": "wri', 12)
        with self.assertRaises(DomainError) as caught:
            self.run_loop([broken] * 5)
        self.assertIn('반복', caught.exception.message)

    def test_a_rewrite_with_unchanged_content_is_reported_and_counts_toward_repetition(self):
        (self.temp / 'ws' / 'tests').mkdir()
        (self.temp / 'ws' / 'tests' / 'test_a.py').write_text('t')
        same = act('write_file', path='tests/test_a.py', content='t', expected_digest=digest('t'))
        script = Script([same, same, same, same])
        with self.assertRaises(DomainError) as caught:
            asyncio.run(BuilderLoop(self.store).run(self.job(), script, self.toolbox()))
        self.assertEqual(len(script.packets), 3)                     # stopped by the one repetition rule, not a special case
        self.assertTrue(script.packets[1]['last_observation']['unchanged'])
        self.assertIn('반복', caught.exception.message)

    def test_the_gate_next_names_the_step_the_ledger_is_waiting_for(self):
        self.codes = [1, 0]
        result, script = self.run_loop([
            act('write_file', path='tests/test_a.py', content='t'), act('run_tests', argv=['python', '-m', 'pytest']),
            act('write_file', path='server/main.py', content='c'), act('run_tests', argv=['python', '-m', 'pytest']), FINISH])
        nexts = [p['gate']['next'] for p in script.packets]
        self.assertIn('실패하는 테스트', nexts[0])
        self.assertIn('run_tests', nexts[1])           # tests written, not run yet
        self.assertIn('구현 파일을 작성', nexts[2])      # RED confirmed
        self.assertIn('run_tests', nexts[3])           # implementation written, not run yet

    def test_action_schema_constrains_every_tool_to_its_own_arguments(self):
        from jsonschema import Draft202012Validator
        validator = Draft202012Validator(action_schema(True))
        for good in (dict(tool='finish', summary='x'), dict(tool='list_files', args={}), dict(tool='read_file', args=dict(path='a')),
                     dict(tool='write_file', args=dict(path='a', content='b')), dict(tool='write_file', args=dict(path='a', content='b', expected_digest=None)),
                     dict(tool='run_tests', args=dict(argv=['python', '-m', 'unittest'], timeout=30)),
                     dict(tool='install_dependencies', args=dict(manager='pip', packages=['x']))):
            validator.validate(good)
        for bad in (dict(tool='rm_rf', args={}), dict(tool='list_files', args=dict(path='.')), dict(tool='read_file', args={}),
                    dict(tool='write_file', args=dict(path='a')), dict(tool='run_command', args=dict(argv='sh -c x')),
                    dict(tool='install_dependencies', args=dict(manager='apt', packages=['x'])), dict(tool='read_file', args=dict(path='a', extra=1)),
                    dict(tool='finish')):
            self.assertFalse(validator.is_valid(bad), bad)

    def test_finish_is_only_offered_in_the_schema_while_the_ledger_allows_it(self):
        self.codes = [1, 0]
        _, script = self.run_loop([
            act('write_file', path='tests/test_a.py', content='t'), act('run_tests', argv=['python', '-m', 'pytest']),
            act('write_file', path='server/main.py', content='c'), act('run_tests', argv=['python', '-m', 'pytest']), FINISH])

        def offers_finish(schema):
            return any(v['properties']['tool'].get('const') == 'finish' for v in schema['anyOf'])
        self.assertEqual([offers_finish(sc) for sc in script.schemas], [False, False, False, False, True])

    def test_a_finish_the_schema_does_not_offer_is_still_refused_with_the_gate_reason(self):
        script = Script([FINISH, act('write_file', path='tests/test_a.py', content='t'), act('read_file', path='x'), FINISH])
        with self.assertRaises(IndexError):
            asyncio.run(BuilderLoop(self.store).run(self.job(), script, self.toolbox()))
        self.assertIn('아직 끝낼 수 없습니다', script.packets[1]['last_observation']['error'])

    def test_instructions_use_placeholders_and_no_task_material(self):
        for placeholder in ('<path>', '<text>', '<runner>'):
            self.assertIn(placeholder, INSTRUCTIONS)
        for material in ('add(', 'reverse', 'Hello', '덧셈', '뒤집'):
            self.assertNotIn(material, INSTRUCTIONS)
        self.assertLess(len(INSTRUCTIONS.encode()), 2200)


if __name__ == '__main__':
    unittest.main()
