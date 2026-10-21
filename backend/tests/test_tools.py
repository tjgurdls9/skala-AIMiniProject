"""F1: workspace tools, command policy, isolation arguments and the immutable tool ledger.

Hermetic: a recording fake executor stands in for Docker; nothing here starts a model or a container.
"""
import os
import sqlite3
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from backend.contracts import DomainError, digest
from backend.store import Store
from runner.commands import (DockerExecutor, CommandResult, TOOL_POLICY, tool_policy_digest, validate_command,
                             validate_install, validate_test_command)
from runner.tools import EscalateToUser, ToolBox
from runner.workspace import MAX_FILE_BYTES, MAX_FILES, Workspace

SECRET_LIKE = 'AKIA' + 'A' * 16


class WorkspaceChecks(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.workspace = Workspace(self.root)

    def code(self, call, *args, **kwargs):
        with self.assertRaises(DomainError) as caught:
            call(*args, **kwargs)
        return caught.exception.code

    def test_write_read_list_roundtrip_with_digest_cas(self):
        created = self.workspace.write('src/a.txt', 'one')
        self.assertEqual(created['content_digest'], digest('one'))
        self.assertEqual(self.workspace.read('src/a.txt')['content'], 'one')
        self.assertEqual(self.code(self.workspace.write, 'src/a.txt', 'two'), 'VERSION_CONFLICT')
        self.assertEqual(self.code(self.workspace.write, 'src/a.txt', 'two', 'sha256:wrong'), 'VERSION_CONFLICT')
        self.workspace.write('src/a.txt', 'two', digest('one'))
        self.assertEqual([f['path'] for f in self.workspace.list_files()], ['src/a.txt'])

    def test_paths_outside_the_workspace_or_into_git_are_refused(self):
        for bad in ('../x', '/abs', 'a\\b', '.git/config', 'a/.git/x', '', '.', 'a/../../x', 'x' * 201, 'a\x00b', 'a\nb'):
            self.assertEqual(self.code(self.workspace.write, bad, 'x'), 'FORBIDDEN', bad)
            self.assertEqual(self.code(self.workspace.read, bad), 'FORBIDDEN', bad)
        self.assertEqual(self.workspace.list_files(), [])

    def test_symlinks_are_never_followed(self):
        outside = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (outside / 'secret.txt').write_text('private')
        os.symlink(outside, self.root / 'link')
        os.symlink(outside / 'secret.txt', self.root / 'file-link')
        self.assertEqual(self.code(self.workspace.read, 'link/secret.txt'), 'FORBIDDEN')
        self.assertEqual(self.code(self.workspace.write, 'link/new.txt', 'x'), 'FORBIDDEN')
        self.assertEqual(self.code(self.workspace.read, 'file-link'), 'FORBIDDEN')
        self.assertEqual(self.code(self.workspace.delete, 'file-link', digest('private')), 'FORBIDDEN')
        self.assertEqual(self.workspace.list_files(), [])
        self.assertFalse((outside / 'new.txt').exists())

    def test_write_scope_limits_mutation_but_not_reading(self):
        scoped = Workspace(self.root, write_scope=('app/**',))
        scoped.write('app/main.txt', 'ok')
        self.assertEqual(self.code(scoped.write, 'other.txt', 'x'), 'FORBIDDEN')
        self.assertEqual(self.code(scoped.delete, 'other.txt', 'sha256:x'), 'FORBIDDEN')
        (self.root / 'other.txt').write_text('seen')
        self.assertEqual(scoped.read('other.txt')['content'], 'seen')

    def test_content_limits_text_only_and_no_secrets(self):
        self.assertEqual(self.code(self.workspace.write, 'big.txt', 'x' * (MAX_FILE_BYTES + 1)), 'INVALID_COMMAND')
        self.assertEqual(self.code(self.workspace.write, 'nul.txt', 'a\x00b'), 'INVALID_COMMAND')
        self.assertEqual(self.code(self.workspace.write, 'key.txt', SECRET_LIKE), 'INVALID_COMMAND')
        self.assertEqual(self.code(self.workspace.write, 'bin.txt', 123), 'INVALID_COMMAND')
        self.assertEqual(self.workspace.list_files(), [])
        (self.root / 'huge.txt').write_text('x' * (MAX_FILE_BYTES + 1))
        self.assertEqual(self.code(self.workspace.read, 'huge.txt'), 'NOT_FOUND')

    def test_file_count_is_bounded(self):
        for index in range(MAX_FILES):
            (self.root / f'f{index}.txt').write_text('x')
        self.assertEqual(self.code(self.workspace.write, 'one-more.txt', 'x'), 'INVALID_COMMAND')
        self.workspace.write('f0.txt', 'y', digest('x'))  # replacing an existing file is still allowed

    def test_delete_and_move_need_the_current_digest(self):
        self.workspace.write('a.txt', 'one')
        self.assertEqual(self.code(self.workspace.delete, 'a.txt', 'sha256:stale'), 'VERSION_CONFLICT')
        moved = self.workspace.move('a.txt', 'dir/b.txt', digest('one'))
        self.assertEqual(moved['content_digest'], digest('one'))
        self.assertFalse((self.root / 'a.txt').exists())
        self.workspace.write('c.txt', 'two')
        self.assertEqual(self.code(self.workspace.move, 'c.txt', 'dir/b.txt', digest('two')), 'VERSION_CONFLICT')
        deleted = self.workspace.delete('dir/b.txt', digest('one'))
        self.assertEqual(deleted['previous_digest'], digest('one'))
        self.assertEqual(self.code(self.workspace.delete, 'dir/b.txt', digest('one')), 'NOT_FOUND')

    def test_manifest_excludes_git_and_changes_with_content(self):
        self.workspace.write('a.txt', 'one')
        (self.root / '.git').mkdir()
        (self.root / '.git' / 'HEAD').write_text('ref')
        before = self.workspace.manifest()
        self.assertEqual(list(before), ['a.txt'])
        self.workspace.write('a.txt', 'two', digest('one'))
        self.assertNotEqual(self.workspace.manifest(), before)


class CommandPolicyChecks(unittest.TestCase):
    def code(self, *args):
        with self.assertRaises(DomainError) as caught:
            validate_command(*args)
        return caught.exception.code

    def test_valid_command_is_normalised(self):
        value = validate_command(['python', '-c', 'print(1); print(2)'], 'sub/dir', 30)
        self.assertEqual(value, dict(argv=['python', '-c', 'print(1); print(2)'], cwd='sub/dir', timeout=30))

    def test_shell_strings_unlisted_and_pathlike_executables_are_refused(self):
        for bad in ('python -m pytest', [], ['sh', '-c', 'x'], ['bash'], ['curl', 'http://x'], ['git', 'status'], ['docker', 'ps'],
                    ['rm', '-rf', '.'], ['/usr/bin/python'], ['./python'], [1], ['python', None], ['python', 'a\x00b']):
            self.assertEqual(self.code(bad, '.', 30), 'FORBIDDEN', bad)

    def test_install_paths_are_closed_so_only_the_install_tool_can_use_the_network(self):
        for bad in (['npm', 'install', 'x'], ['npm', 'i'], ['npm', 'ci'], ['npm', 'exec', 'x'], ['python', '-m', 'pip', 'install', 'x'],
                    ['pip', 'install', 'x']):
            self.assertEqual(self.code(bad, '.', 30), 'FORBIDDEN', bad)

    def test_cwd_timeout_and_size_bounds(self):
        for cwd in ('..', '/abs', 'a/../..', '.git', ''):
            self.assertEqual(self.code(['python'], cwd, 30), 'FORBIDDEN', cwd)
        for timeout in (0, -1, TOOL_POLICY['timeout_max'] + 1, '30', 1.5, True):
            self.assertEqual(self.code(['python'], '.', timeout), 'INVALID_COMMAND', timeout)
        self.assertEqual(self.code(['python'] + ['x'] * TOOL_POLICY['max_args'], '.', 30), 'INVALID_COMMAND')
        self.assertEqual(self.code(['python', 'x' * (TOOL_POLICY['arg_bytes'] + 1)], '.', 30), 'INVALID_COMMAND')

    def test_test_commands_must_be_a_known_runner_form(self):
        for good in (['python', '-m', 'pytest', '-q'], ['python', '-m', 'unittest', 'discover'], ['node', '--test'], ['npm', 'test'],
                     ['npm', 'run', 'test']):
            validate_test_command(good)
        for bad in (['python', '-c', 'import sys; sys.exit(1)'], ['python', 'tests.py'], ['npm', 'run', 'build'], ['node', 'x.js']):
            with self.assertRaises(DomainError) as caught:
                validate_test_command(bad)
            self.assertEqual(caught.exception.code, 'FORBIDDEN', bad)

    def test_install_requests_are_plain_registry_names_only(self):
        self.assertEqual(validate_install('pip', ['fastapi==0.115.0', 'uvicorn']), ['fastapi==0.115.0', 'uvicorn'])
        self.assertEqual(validate_install('npm', ['vue@3.5.0', '@scope/pkg']), ['vue@3.5.0', '@scope/pkg'])
        for manager, packages in (('apt', ['x']), ('pip', []), ('pip', ['x'] * 21), ('pip', ['git+https://x/y']), ('pip', ['./local']),
                                  ('pip', ['http://x/y.whl']), ('pip', ['x;rm']), ('pip', ['-r requirements.txt']), ('npm', ['github:a/b']),
                                  ('npm', ['file:../x']), ('npm', ['../x']), ('npm', ['x y']), ('pip', [1]), ('pip', 'fastapi')):
            with self.assertRaises(DomainError, msg=(manager, packages)):
                validate_install(manager, packages)

    def test_policy_digest_is_stable_and_tracks_the_policy(self):
        self.assertEqual(tool_policy_digest(), tool_policy_digest())
        self.assertTrue(tool_policy_digest().startswith('sha256:'))
        self.assertNotEqual(tool_policy_digest(), digest(dict(TOOL_POLICY, timeout_max=1)))


class FakeProcess:
    def __init__(self, returncode=0, stdout=b'', stderr=b''):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


class DockerExecutorChecks(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.workspace = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.reply = FakeProcess(0, b'ok\n', b'')

        def runner(args, **kwargs):
            self.calls.append((args, kwargs))
            if isinstance(self.reply, Exception) and args[1] == 'run':
                raise self.reply
            return self.reply if not isinstance(self.reply, Exception) else FakeProcess()
        self.executor = DockerExecutor('python@sha256:' + 'a' * 64, runner=runner)

    def test_container_is_isolated_and_argv_stays_one_element_per_argument(self):
        self.executor.run(self.workspace, ['python', '-c', 'print(1); print(2)'], 'sub', 30, network='none')
        args, kwargs = self.calls[0]
        text = ' '.join(args)
        for needle in ('--network none', '--read-only', '--cap-drop ALL', '--user 65534:65534', '--security-opt no-new-privileges',
                       '--pids-limit', '--memory 512m', '--memory-swap 512m', '--workdir /work/sub'):
            self.assertIn(needle, text)
        for forbidden in ('--privileged', 'docker.sock', '--volume', ' -v ', '--env-file', '--pid host', '--net host'):
            self.assertNotIn(forbidden, text)
        mounts = [args[i + 1] for i, a in enumerate(args) if a == '--mount']
        self.assertEqual(mounts, [f'type=bind,src={self.workspace},dst=/work'])
        self.assertEqual(args[-3:], ['python', '-c', 'print(1); print(2)'])
        self.assertIs(kwargs.get('shell', False), False)
        self.assertNotIn('env', kwargs)  # the host environment is never forwarded into the container
        env_pairs = [args[i + 1] for i, a in enumerate(args) if a == '--env']
        self.assertEqual(env_pairs, ['HOME=/tmp'])

    def test_only_a_named_registry_network_is_ever_passed_and_never_host_env(self):
        self.executor.run(self.workspace, ['python'], '.', 30, network='lifecycle-registry', env=dict(HTTPS_PROXY='http://proxy:3128'))
        args, _ = self.calls[0]
        self.assertIn('--network lifecycle-registry', ' '.join(args))
        self.assertIn('HTTPS_PROXY=http://proxy:3128', args)
        env_pairs = [args[i + 1] for i, a in enumerate(args) if a == '--env']
        self.assertEqual(env_pairs, ['HOME=/tmp', 'HTTPS_PROXY=http://proxy:3128'])

    def test_exit_code_output_cap_and_redaction(self):
        self.reply = FakeProcess(3, b'x' * 70000, ('leak ' + SECRET_LIKE).encode())
        result = self.executor.run(self.workspace, ['python'], '.', 30)
        self.assertEqual(result.exit_code, 3)
        self.assertTrue(result.truncated)
        self.assertEqual(len(result.stdout.encode()), TOOL_POLICY['output_bytes'])
        self.assertNotIn(SECRET_LIKE, result.stderr)

    def test_timeout_kills_the_named_container(self):
        import subprocess
        self.reply = subprocess.TimeoutExpired('docker', 30)
        result = self.executor.run(self.workspace, ['python'], '.', 30)
        self.assertTrue(result.timed_out)
        self.assertIsNone(result.exit_code)
        self.assertEqual(self.calls[-1][0][:3], ['docker', 'rm', '-f'])
        name = self.calls[0][0][self.calls[0][0].index('--name') + 1]
        self.assertEqual(self.calls[-1][0][3], name)

    def test_image_must_be_digest_pinned(self):
        for image in ('python:latest', 'python', 'python@sha256:short'):
            with self.assertRaises(DomainError):
                DockerExecutor(image)


class ImageSelectionChecks(unittest.TestCase):
    PY = 'python@sha256:' + 'a' * 64
    NODE = 'node@sha256:' + 'b' * 64

    def run_with(self, argv, images):
        calls = []

        def runner(args, **kwargs):
            calls.append(args)
            return FakeProcess()
        DockerExecutor(images, runner=runner).run(Path('/tmp'), argv, '.', 30)
        return calls[0]

    def test_each_program_runs_in_the_image_of_its_language(self):
        images = dict(python=self.PY, node=self.NODE)
        for argv, expected in ((['python', '-c', 'x'], self.PY), (['python3', '-m', 'pytest'], self.PY),
                               (['node', '-e', 'x'], self.NODE), (['npm', 'test'], self.NODE)):
            args = self.run_with(argv, images)
            self.assertIn(expected, args)
            self.assertEqual(args.index(expected), len(args) - len(argv) - 1, argv)

    def test_an_unmapped_program_or_a_bad_image_map_is_refused(self):
        with self.assertRaises(DomainError):
            self.run_with(['npm', 'test'], dict(python=self.PY))
        with self.assertRaises(DomainError):
            DockerExecutor(dict(python='python:latest'))
        with self.assertRaises(DomainError):
            DockerExecutor({})


class RegistryProxyIsolationChecks(unittest.TestCase):
    def test_proxy_runs_with_the_standard_library_only(self):
        import subprocess
        import sys
        code = "import sys, runner.registry_proxy; assert not {'runner.commands', 'backend.contracts', 'jsonschema'} & set(sys.modules)"
        done = subprocess.run([sys.executable, '-c', code], cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_policy_and_proxy_share_one_host_list(self):
        from runner.registry_hosts import REGISTRY_HOSTS
        self.assertEqual(list(REGISTRY_HOSTS), TOOL_POLICY['registry_hosts'])


class RecordingExecutor:
    def __init__(self):
        self.calls = []
        self.result = CommandResult(exit_code=0, stdout='ok', stderr='', timed_out=False, truncated=False)

    def run(self, workspace, argv, cwd, timeout, network='none', env=None, deps=None, deps_writable=False):
        self.calls.append(dict(argv=argv, cwd=cwd, timeout=timeout, network=network, env=env, deps=deps, deps_writable=deps_writable))
        return self.result


class ToolBoxChecks(unittest.TestCase):
    def setUp(self):
        self.temp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.store = Store(self.temp / 'state.sqlite3')
        project = self.store.project(dict(title='synthetic', request='generic request'))
        self.run_id = self.store.create_run(project['project_id'], dict(mode='live'))['run_id']
        self.root = self.temp / 'ws'
        self.root.mkdir()
        self.executor = RecordingExecutor()
        self.who = dict(role='builder', run_id=self.run_id, job_id='job1', attempt_id='att1', task_id='task1')
        self.box = self.make()

    def make(self, **kwargs):
        return ToolBox(lambda: self.who, self.store, Workspace(self.root), self.executor, **{'deps_dir': self.temp / 'deps', **kwargs})

    def entries(self):
        return self.store.tool_calls(self.run_id)

    def test_every_call_is_recorded_in_order_without_file_content(self):
        self.box.write_file('app/a.txt', 'private body')
        self.box.read_file('app/a.txt')
        self.box.list_files()
        entries = self.entries()
        self.assertEqual([e['tool'] for e in entries], ['write_file', 'read_file', 'list_files'])
        self.assertEqual([e['seq'] for e in entries], [1, 2, 3])
        self.assertTrue(all(e['ok'] for e in entries))
        self.assertTrue(all(e['role'] == 'builder' and e['task_id'] == 'task1' and e['attempt_id'] == 'att1' for e in entries))
        self.assertNotIn('private body', str([e['args'] for e in entries]))
        self.assertEqual(entries[0]['args']['content_digest'], digest('private body'))
        self.assertEqual(entries[0]['args']['content_bytes'], len('private body'))

    def test_denied_calls_are_recorded_too(self):
        with self.assertRaises(DomainError):
            self.box.write_file('../escape.txt', 'x')
        entry = self.entries()[0]
        self.assertFalse(entry['ok'])
        self.assertEqual(entry['error_code'], 'FORBIDDEN')
        self.assertFalse((self.temp / 'escape.txt').exists())

    def test_non_builder_roles_cannot_mutate_or_execute(self):
        self.box.write_file('a.txt', 'one')
        for role in ('validator', 'security', 'planner'):
            self.who = dict(self.who, role=role)
            for call in (lambda: self.box.write_file('b.txt', 'x'), lambda: self.box.delete_file('a.txt', digest('one')),
                         lambda: self.box.move_file('a.txt', 'c.txt', digest('one')), lambda: self.box.run_command(['python']),
                         lambda: self.box.run_tests(['python', '-m', 'pytest']), lambda: self.box.install_dependencies('pip', ['x'])):
                with self.assertRaises(DomainError) as caught:
                    call()
                self.assertEqual(caught.exception.code, 'FORBIDDEN')
        self.assertTrue((self.root / 'a.txt').exists())
        self.assertEqual(self.executor.calls, [])
        self.who = dict(self.who, role='validator')
        self.assertEqual(self.box.read_file('a.txt')['content'], 'one')

    def test_revoked_authority_stops_the_call_and_records_nothing(self):
        def revoked():
            raise DomainError('FORBIDDEN', '작업 권한이 만료됐습니다.', 403)
        box = ToolBox(revoked, self.store, Workspace(self.root), self.executor)
        with self.assertRaises(DomainError):
            box.write_file('a.txt', 'x')
        self.assertEqual(self.entries(), [])
        self.assertFalse((self.root / 'a.txt').exists())

    def test_run_command_records_exit_code_and_output_digests(self):
        self.executor.result = CommandResult(exit_code=2, stdout='out', stderr='err ' + SECRET_LIKE, timed_out=False, truncated=False)
        result = self.box.run_command(['python', '-c', 'x'], cwd='.', timeout=20)
        self.assertEqual(result['exit_code'], 2)
        entry = self.entries()[0]
        self.assertTrue(entry['ok'])
        self.assertEqual((entry['exit_code'], entry['stdout_digest'], entry['stderr_digest']), (2, digest('out'), digest('err ' + SECRET_LIKE)))
        self.assertNotIn(SECRET_LIKE, str(entry))
        self.assertEqual(self.executor.calls[0]['network'], 'none')

    def test_links_a_program_leaves_in_the_workspace_are_removed_and_reported(self):
        outside = self.temp / 'host-secret.txt'
        outside.write_text('private')
        root = self.root

        class Planting(RecordingExecutor):
            def run(self, workspace, argv, cwd, timeout, **kwargs):
                os.symlink(outside, root / 'leak')
                (root / 'sub').mkdir(exist_ok=True)
                os.symlink(root, root / 'sub' / 'loop')
                os.mkfifo(root / 'pipe')
                return super().run(workspace, argv, cwd, timeout, **kwargs)
        self.executor = Planting()
        box = self.make()
        result = box.run_command(['python', '-c', 'x'])
        self.assertEqual(result['removed_links'], ['leak', 'pipe', 'sub/loop'])
        self.assertFalse((self.root / 'leak').is_symlink())
        self.assertEqual(outside.read_text(), 'private')
        self.assertEqual(box.list_files(), dict(files=[]))

    def test_run_tests_only_accepts_test_runner_forms_and_is_ledgered_as_such(self):
        with self.assertRaises(DomainError):
            self.box.run_tests(['python', '-c', 'import sys; sys.exit(1)'])
        self.box.run_tests(['python', '-m', 'unittest', 'discover'])
        self.assertEqual([e['tool'] for e in self.entries()], ['run_tests', 'run_tests'])
        self.assertEqual([e['ok'] for e in self.entries()], [False, True])
        self.assertEqual(len(self.executor.calls), 1)

    def test_install_needs_a_plan_allowlist_and_a_configured_registry_network(self):
        with self.assertRaises(EscalateToUser):
            self.box.install_dependencies('pip', ['fastapi'])          # no approved dependency range at all
        box = self.make(allowed_dependencies={'pip': {'fastapi'}})
        with self.assertRaises(EscalateToUser):
            box.install_dependencies('pip', ['requests'])              # outside the approved range
        with self.assertRaises(DomainError) as caught:
            box.install_dependencies('pip', ['fastapi'])               # registry network not configured
        self.assertEqual(caught.exception.code, 'RUNTIME_UNAVAILABLE')
        self.assertEqual(self.executor.calls, [])

    def test_install_runs_on_the_registry_network_then_freezes_offline(self):
        box = self.make(allowed_dependencies={'pip': {'fastapi'}}, registry_network='lifecycle-registry',
                        registry_env=dict(HTTPS_PROXY='http://proxy:3128'))
        self.executor.result = CommandResult(exit_code=0, stdout='fastapi==0.115.0\n', stderr='', timed_out=False, truncated=False)
        result = box.install_dependencies('pip', ['fastapi'])
        install, freeze = self.executor.calls
        self.assertEqual(install['network'], 'lifecycle-registry')
        self.assertIn('--only-binary=:all:', install['argv'])
        self.assertEqual(freeze['network'], 'none')
        self.assertEqual(result['lock_file'], 'requirements.lock')
        self.assertEqual(self.box_read('requirements.lock'), 'fastapi==0.115.0\n')
        self.assertEqual([e['tool'] for e in self.entries()], ['install_dependencies'])

    def test_npm_install_never_runs_package_scripts(self):
        box = self.make(allowed_dependencies={'npm': {'vue'}}, registry_network='lifecycle-registry')
        box.install_dependencies('npm', ['vue@3.5.0'])
        self.assertIn('--ignore-scripts', self.executor.calls[0]['argv'])
        self.assertEqual(self.executor.calls[0]['network'], 'lifecycle-registry')

    def box_read(self, name):
        return (self.root / name).read_text()


class StubScope:
    """Stands in for a server-issued RoleScope; production binding is exercised by the real MCP handshake test."""
    def __init__(self, role, workspace=None, options=None):
        import json
        self.row = dict(role=role, run_id='run', job_id='job', attempt_id='att', workspace=str(workspace) if workspace else None,
                        context=json.dumps(dict(options=options or {})))

    def authority(self, db=None):
        return self.row, None


class ToolBoxGateChecks(unittest.TestCase):
    """The server, not the model, decides when implementation files may be written."""

    def setUp(self):
        self.temp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.store = Store(self.temp / 'state.sqlite3')
        project = self.store.project(dict(title='synthetic', request='generic request'))
        self.run_id = self.store.create_run(project['project_id'], dict(mode='live'))['run_id']
        (self.temp / 'ws').mkdir()
        self.executor = RecordingExecutor()
        self.who = dict(role='builder', run_id=self.run_id, job_id='j', attempt_id='a', task_id='t1', task_kind='backend')
        self.box = ToolBox(lambda: self.who, self.store, Workspace(self.temp / 'ws'), self.executor, deps_dir=self.temp / 'deps')

    def result(self, code):
        self.executor.result = CommandResult(exit_code=code, stdout='', stderr='', timed_out=code is None, truncated=False)

    def test_implementation_is_refused_until_a_real_failing_test_run_is_recorded(self):
        with self.assertRaises(DomainError) as caught:
            self.box.write_file('server/main.py', 'code')
        self.assertEqual(caught.exception.code, 'FORBIDDEN')
        self.assertIn('실패하는 테스트', caught.exception.message)
        self.assertFalse((self.temp / 'ws' / 'server').exists())
        self.box.write_file('tests/test_a.py', 'test')
        self.result(0)
        self.box.run_tests(['python', '-m', 'pytest'])                         # passes immediately: not RED
        with self.assertRaises(DomainError):
            self.box.write_file('server/main.py', 'code')
        self.result(1)
        self.box.run_tests(['python', '-m', 'pytest'])                         # genuine failure: RED
        self.box.write_file('server/main.py', 'code')
        self.assertTrue((self.temp / 'ws' / 'server' / 'main.py').exists())
        self.assertEqual([e['ok'] for e in self.store.tool_calls(self.run_id) if e['tool'] == 'write_file'], [False, True, False, True])

    def test_only_this_tasks_ledger_opens_the_gate(self):
        self.box.write_file('tests/test_a.py', 'test')
        self.result(1)
        self.box.run_tests(['python', '-m', 'pytest'])
        self.who = dict(self.who, task_id='t2')                                # another task has its own RED to earn
        with self.assertRaises(DomainError):
            self.box.write_file('server/other.py', 'code')

    def test_tasks_without_a_test_phase_are_not_gated(self):
        self.who = dict(self.who, task_kind='contract')
        self.box.write_file('contract/api.json', '{}')
        self.who = dict(self.who, task_kind=None)
        self.box.write_file('anything.txt', 'x')

    def test_deleting_or_moving_implementation_is_gated_like_writing_it(self):
        (self.temp / 'ws' / 'server').mkdir()
        (self.temp / 'ws' / 'server' / 'main.py').write_text('old')
        with self.assertRaises(DomainError):
            self.box.delete_file('server/main.py', digest('old'))
        with self.assertRaises(DomainError):
            self.box.move_file('server/main.py', 'server/other.py', digest('old'))


class ToolBoxSemantics(unittest.TestCase):
    """Behaviour found by running the real model: infrastructure errors are not test results; reads remember digests."""

    def setUp(self):
        self.temp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.store = Store(self.temp / 'state.sqlite3')
        project = self.store.project(dict(title='synthetic', request='generic request'))
        self.run_id = self.store.create_run(project['project_id'], dict(mode='live'))['run_id']
        (self.temp / 'ws').mkdir()
        self.executor = RecordingExecutor()
        self.who = dict(role='builder', run_id=self.run_id, job_id='j', attempt_id='a', task_id='t1', task_kind='backend')
        self.box = ToolBox(lambda: self.who, self.store, Workspace(self.temp / 'ws'), self.executor, deps_dir=self.temp / 'deps')

    def test_docker_level_exit_codes_are_infrastructure_errors_never_failing_tests(self):
        for code in (125, 126, 127):
            self.executor.result = CommandResult(code, '', 'docker: Error response from daemon: invalid mount config', False, False)
            with self.assertRaises(DomainError) as caught:
                self.box.run_tests(['python', '-m', 'unittest'])
            self.assertEqual(caught.exception.code, 'RUNTIME_UNAVAILABLE')
        entries = self.store.tool_calls(self.run_id)
        self.assertEqual([(e['tool'], e['ok'], e['error_code']) for e in entries], [('run_tests', False, 'RUNTIME_UNAVAILABLE')] * 3)
        from runner.tdd_gate import progress
        self.box.write_file('tests/test_a.py', 't')
        self.executor.result = CommandResult(125, '', 'x', False, False)
        with self.assertRaises(DomainError):
            self.box.run_tests(['python', '-m', 'unittest'])
        self.assertEqual(progress(self.store.tool_calls(self.run_id, 't1'), 'backend').phase, 'red')   # no RED from a broken container

    def test_a_real_test_failure_with_an_ordinary_exit_code_is_still_a_result(self):
        self.executor.result = CommandResult(1, 'FAIL', '', False, False)
        self.assertEqual(self.box.run_tests(['python', '-m', 'unittest'])['exit_code'], 1)

    def test_overwriting_a_file_the_model_has_just_seen_needs_no_digest_plumbing(self):
        self.box.write_file('tests/test_a.py', 'one')
        self.box.write_file('tests/test_a.py', 'two')                      # the box knows the digest it just wrote
        self.assertEqual(self.box.read_file('tests/test_a.py')['content'], 'two')
        (self.temp / 'ws' / 'tests' / 'test_a.py').write_text('changed outside')
        with self.assertRaises(DomainError) as caught:                      # but never blindly over an unseen change
            self.box.write_file('tests/test_a.py', 'three')
        self.assertEqual(caught.exception.code, 'VERSION_CONFLICT')
        self.box.read_file('tests/test_a.py')
        self.box.write_file('tests/test_a.py', 'three')
        self.assertEqual((self.temp / 'ws' / 'tests' / 'test_a.py').read_text(), 'three')

    def test_a_file_never_seen_still_needs_the_digest_and_list_files_counts_as_seeing(self):
        self.who = dict(self.who, task_kind=None)           # the RED gate is not what this test is about
        (self.temp / 'ws' / 'old.txt').write_text('old')
        with self.assertRaises(DomainError):
            self.box.write_file('old.txt', 'new')
        self.box.list_files()
        self.box.write_file('old.txt', 'new')
        self.assertEqual((self.temp / 'ws' / 'old.txt').read_text(), 'new')

    def test_an_explicit_wrong_digest_is_still_a_conflict(self):
        self.who = dict(self.who, task_kind=None)           # the RED gate is not what this test is about
        self.box.write_file('a.txt', 'one')
        with self.assertRaises(DomainError):
            self.box.write_file('a.txt', 'two', 'sha256:wrong')

    def test_rejected_test_forms_name_the_allowed_ones(self):
        with self.assertRaises(DomainError) as caught:
            self.box.run_tests(['python', 'test_a.py'])
        for form in ('python -m unittest', 'python -m pytest', 'node --test', 'npm test'):
            self.assertIn(form, caught.exception.message)


class McpWiringChecks(unittest.TestCase):
    def setUp(self):
        self.temp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.store = Store(self.temp / 'state.sqlite3')
        project = self.store.project(dict(title='synthetic', request='generic request'))
        self.run_id = self.store.create_run(project['project_id'], dict(mode='live'))['run_id']
        (self.temp / 'ws').mkdir()

    def server(self, role, options=None, with_toolbox=True):
        import asyncio
        from runner.mcp_server import create_server
        scope = StubScope(role, self.temp / 'ws', options)
        scope.row['run_id'] = self.run_id
        toolbox = ToolBox.from_scope(self.store, scope, RecordingExecutor()) if with_toolbox else None
        return asyncio.run, create_server(scope, corpus=None, toolbox=toolbox)

    def names(self, role, **kwargs):
        run, server = self.server(role, **kwargs)
        return {t.name for t in run(server.list_tools())}

    def test_only_the_builder_gets_mutating_and_executing_tools(self):
        mutating = {'write_file', 'delete_file', 'move_file', 'run_command', 'run_tests', 'install_dependencies'}
        self.assertTrue(mutating <= self.names('builder'))
        for role in ('validator', 'security'):
            self.assertEqual(self.names(role) & mutating, set())
            self.assertTrue({'list_files', 'read_file'} <= self.names(role))
        self.assertEqual(self.names('planner') & (mutating | {'list_files', 'read_file'}), set())

    def test_without_a_toolbox_the_legacy_patch_tool_is_unchanged(self):
        self.assertIn('patch_file', self.names('builder', with_toolbox=False))
        self.assertNotIn('write_file', self.names('builder', with_toolbox=False))

    def test_tool_call_through_mcp_writes_inside_scope_and_is_ledgered(self):
        run, server = self.server('builder', options=dict(task_id='t1', write_scope=['app/**']))
        run(server.call_tool('write_file', dict(path='app/x.txt', content='hello')))
        self.assertEqual((self.temp / 'ws' / 'app' / 'x.txt').read_text(), 'hello')
        with self.assertRaises(Exception):
            run(server.call_tool('write_file', dict(path='outside.txt', content='no')))
        entries = self.store.tool_calls(self.run_id)
        self.assertEqual([(e['tool'], e['ok'], e['task_id']) for e in entries], [('write_file', True, 't1'), ('write_file', False, 't1')])
        self.assertFalse((self.temp / 'ws' / 'outside.txt').exists())


class RegistryProxyChecks(unittest.TestCase):
    def test_only_public_registry_hosts_on_443_are_tunnelled(self):
        from runner.registry_proxy import parse_connect, target_allowed
        self.assertTrue(target_allowed(parse_connect('CONNECT pypi.org:443 HTTP/1.1')))
        self.assertTrue(target_allowed(parse_connect('CONNECT registry.npmjs.org:443 HTTP/1.1')))
        self.assertTrue(target_allowed(parse_connect('CONNECT FILES.PYTHONHOSTED.ORG:443 HTTP/1.1')))
        for line in ('CONNECT pypi.org:80 HTTP/1.1', 'CONNECT evil.example:443 HTTP/1.1', 'CONNECT pypi.org.evil.example:443 HTTP/1.1',
                     'GET http://pypi.org/ HTTP/1.1', 'CONNECT pypi.org HTTP/1.1', 'CONNECT 127.0.0.1:443 HTTP/1.1', 'CONNECT a:b:443 HTTP/1.1',
                     'CONNECT pypi.org:443 SPDY', ''):
            self.assertFalse(target_allowed(parse_connect(line)), line)


class RegistryProxyNetworkChecks(unittest.IsolatedAsyncioTestCase):
    """Loopback only: the upstream is a local echo server, never a real registry."""

    async def start(self):
        import asyncio
        from runner import registry_proxy
        self.logged = []
        self.enterContext(unittest.mock.patch.object(registry_proxy, 'log', lambda **f: self.logged.append(f)))
        proxy = await asyncio.start_server(registry_proxy.handle, '127.0.0.1', 0)
        self.addAsyncCleanup(self._close, proxy)
        return proxy.sockets[0].getsockname()[1]

    @staticmethod
    async def _close(server):
        server.close()
        await server.wait_closed()

    async def echo_server(self):
        import asyncio

        async def echo(reader, writer):
            writer.write(await reader.read(100))
            await writer.drain()
            writer.close()
        server = await asyncio.start_server(echo, '127.0.0.1', 0)
        self.addAsyncCleanup(self._close, server)
        return server.sockets[0].getsockname()[1]

    async def connect(self, port, request=None):
        import asyncio
        reader, writer = await asyncio.open_connection('127.0.0.1', port)
        if request is not None:
            await self.send(writer, request)
        return reader, writer

    @staticmethod
    async def send(writer, request):
        writer.write(request.encode())
        await writer.drain()

    async def test_disallowed_target_is_refused_with_403_and_logged(self):
        port = await self.start()
        reader, writer = await self.connect(port, 'CONNECT evil.example:443 HTTP/1.1\r\nHost: x\r\n\r\n')
        self.assertIn(b'403', await reader.readline())
        writer.close()
        self.assertEqual(self.logged[0]['event'], 'refused')

    async def test_allowed_target_is_tunnelled_both_ways(self):
        import asyncio
        upstream = await self.echo_server()
        port = await self.start()
        real = asyncio.open_connection

        async def to_echo(host, remote_port):
            self.assertEqual((host, remote_port), ('pypi.org', 443))
            return await real('127.0.0.1', upstream)
        reader, writer = await self.connect(port)  # the client connects for real; only the proxy's upstream is redirected
        with unittest.mock.patch.object(asyncio, 'open_connection', to_echo):
            await self.send(writer, 'CONNECT pypi.org:443 HTTP/1.1\r\n\r\n')
            self.assertIn(b'200', await reader.readline())
        await reader.readline()
        writer.write(b'ping')
        await writer.drain()
        self.assertEqual(await reader.read(100), b'ping')
        writer.close()
        self.assertEqual(self.logged[0]['event'], 'tunnel')

    async def test_unreachable_upstream_is_a_502_not_a_hang(self):
        import asyncio
        port = await self.start()

        async def fail(host, remote_port):
            raise OSError('unreachable')
        reader, writer = await self.connect(port)
        with unittest.mock.patch.object(asyncio, 'open_connection', fail):
            await self.send(writer, 'CONNECT pypi.org:443 HTTP/1.1\r\n\r\n')
            self.assertIn(b'502', await reader.readline())
        writer.close()


class FreezeGuardChecks(unittest.TestCase):
    def test_a_workspace_with_a_symlink_is_never_frozen_into_a_candidate(self):
        from runner.sandbox import Sandbox
        temp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        workspace = temp / 'ws'
        workspace.mkdir()
        os.symlink(temp, workspace / 'link')
        with self.assertRaises(DomainError) as caught:
            Sandbox(temp / 'root').freeze(workspace)
        self.assertEqual(caught.exception.code, 'FORBIDDEN')
        self.assertFalse((temp / 'root' / 'candidates').exists() and any((temp / 'root' / 'candidates').iterdir()))


class LedgerChecks(unittest.TestCase):
    def setUp(self):
        self.temp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.store = Store(self.temp / 'state.sqlite3')
        project = self.store.project(dict(title='synthetic', request='generic request'))
        self.run_id = self.store.create_run(project['project_id'], dict(mode='live'))['run_id']

    def test_ledger_rows_cannot_be_updated_or_deleted(self):
        self.store.record_tool_call(dict(run_id=self.run_id, role='builder', tool='list_files', args={}, ok=True))
        with self.assertRaises(sqlite3.IntegrityError), self.store.transaction() as db:
            db.execute("UPDATE tool_calls SET ok=0")
        with self.assertRaises(sqlite3.IntegrityError), self.store.transaction() as db:
            db.execute("DELETE FROM tool_calls")

    def test_sequence_is_per_run_and_monotonic(self):
        for _ in range(3):
            self.store.record_tool_call(dict(run_id=self.run_id, role='builder', tool='list_files', args={}, ok=True))
        self.assertEqual([e['seq'] for e in self.store.tool_calls(self.run_id)], [1, 2, 3])


if __name__ == '__main__':
    unittest.main()
