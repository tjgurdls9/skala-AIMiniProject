"""F4b: per-task commits with kept history, and a generic candidate freeze from an app declaration (docker is faked)."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from backend.contracts import DomainError, digest
from runner.candidate import APP_FILE, commit_task, freeze_model, git_dir_of, render_dockerfile, validate_app_manifest

BASE = 'python@sha256:' + 'a' * 64
APP = dict(runtime='python', start=['python', '-m', 'http.server', '8080'], port=8080, health='/')


class Engine:
    """Stands in for Sandbox: records docker calls and writes the image id file a real build would."""
    def __init__(self, root):
        self.root, self.calls = Path(root), []

    def docker(self, *args, timeout=120):
        self.calls.append([str(a) for a in args])
        if args[0] == 'build':
            Path(args[args.index('--iidfile') + 1]).write_text('sha256:' + 'c' * 64)
        return ''


def log(workspace):
    done = subprocess.run(['git', '--git-dir', str(git_dir_of(workspace)), 'log', '--format=%H|%s'], capture_output=True, text=True)
    return [line.split('|', 1) for line in done.stdout.splitlines()]


class CommitChecks(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.workspace = self.root / 'ws'
        self.workspace.mkdir()

    def test_each_task_adds_a_commit_and_history_is_kept(self):
        (self.workspace / 'a.txt').write_text('one')
        first = commit_task(self.workspace, 'task-1', '첫 작업')
        (self.workspace / 'b.txt').write_text('two')
        second = commit_task(self.workspace, 'task-2', '둘째 작업')
        history = log(self.workspace)
        self.assertEqual([h[0] for h in history], [second, first])
        self.assertIn('task-2', history[0][1])
        self.assertIn('둘째 작업', history[0][1])

    def test_a_task_without_changes_adds_nothing(self):
        (self.workspace / 'a.txt').write_text('one')
        first = commit_task(self.workspace, 'task-1', '첫 작업')
        self.assertEqual(commit_task(self.workspace, 'task-2', '변경 없음'), first)
        self.assertEqual(len(log(self.workspace)), 1)

    def test_the_repository_lives_outside_the_workspace_the_sandbox_can_write(self):
        (self.workspace / 'a.txt').write_text('one')
        commit_task(self.workspace, 'task-1', '첫 작업')
        self.assertFalse((self.workspace / '.git').exists())
        self.assertTrue(git_dir_of(self.workspace).is_dir())
        self.assertFalse(str(git_dir_of(self.workspace)).startswith(str(self.workspace) + os.sep))

    def test_hooks_and_attribute_filters_cannot_run_host_code(self):
        (self.workspace / 'a.txt').write_text('one')
        commit_task(self.workspace, 'task-1', '첫 작업')
        marker = self.root / 'ran'
        hook = git_dir_of(self.workspace) / 'hooks' / 'pre-commit'
        hook.parent.mkdir(exist_ok=True)
        hook.write_text(f'#!/bin/sh\ntouch {marker}\n')
        hook.chmod(0o755)
        (self.workspace / '.gitattributes').write_text('* filter=evil\n')           # no filter driver exists, so nothing may run
        (self.workspace / 'b.txt').write_text('two')
        commit_task(self.workspace, 'task-2', '둘째 작업')
        self.assertFalse(marker.exists())

    def test_huge_or_non_regular_files_are_not_committed(self):
        (self.workspace / 'a.txt').write_text('one')
        os.mkfifo(self.workspace / 'pipe')
        commit_task(self.workspace, 'task-1', '첫 작업')
        names = subprocess.run(['git', '--git-dir', str(git_dir_of(self.workspace)), 'ls-tree', '-r', '--name-only', 'HEAD'],
                               capture_output=True, text=True).stdout.split()
        self.assertEqual(names, ['a.txt'])


class ManifestChecks(unittest.TestCase):
    def test_valid_declarations(self):
        self.assertEqual(validate_app_manifest(APP), APP)
        validate_app_manifest(dict(runtime='node', start=['node', 'server.js'], port=8080, health='/health'))

    def test_invalid_declarations_are_refused(self):
        for bad in (dict(APP, runtime='ruby'), dict(APP, start=['sh', '-c', 'x']), dict(APP, start='python app.py'), dict(APP, start=[]),
                    dict(APP, port=3000), dict(APP, health='health'), dict(APP, extra=1), {k: v for k, v in APP.items() if k != 'start'},
                    dict(APP, start=['npm', 'install']), 'not a dict'):
            with self.assertRaises(DomainError, msg=bad):
                validate_app_manifest(bad)

    def test_dockerfile_is_generated_from_the_validated_declaration_only(self):
        text = render_dockerfile(BASE, APP)
        self.assertIn(f'FROM {BASE}', text)
        self.assertIn('USER 65534:65534', text)
        self.assertIn('CMD ["python", "-m", "http.server", "8080"]', text)
        self.assertIn('PYTHONPATH=/deps/py', text)
        self.assertNotIn('RUN ', text)                  # nothing is installed or executed while building
        with self.assertRaises(DomainError):
            render_dockerfile('python:latest', APP)


class FreezeChecks(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.workspace = self.root / 'ws'
        self.deps = self.root / 'ws.deps'
        (self.workspace / 'server').mkdir(parents=True)
        (self.deps / 'py').mkdir(parents=True)
        (self.deps / 'py' / 'lib.py').write_text('x = 1')
        (self.workspace / 'server' / 'main.py').write_text('print(1)')
        (self.workspace / APP_FILE).write_text(json.dumps(APP))
        self.engine = Engine(self.root / 'engine')

    def test_freeze_commits_clones_and_builds_offline_from_a_generated_dockerfile(self):
        commit_task(self.workspace, 'task-1', '작업')
        candidate = freeze_model(self.engine, self.workspace, self.deps, BASE)
        head = log(self.workspace)[0][0]
        self.assertEqual(candidate['commit_sha'], head)
        self.assertEqual(candidate['image_digest'], 'sha256:' + 'c' * 64)
        self.assertEqual(sorted(candidate['manifest']), [APP_FILE, 'server/main.py'])
        self.assertTrue((Path(candidate['path']) / 'server' / 'main.py').exists())
        build = next(c for c in self.engine.calls if c[0] == 'build')
        self.assertIn('--network=none', build)
        self.assertEqual(candidate['app'], APP)

    def test_the_build_context_has_the_app_and_dependencies_but_never_git_data(self):
        commit_task(self.workspace, 'task-1', '작업')
        seen = {}

        def docker(*args, timeout=120):
            if args[0] == 'build':
                context = Path(args[-1])
                seen.update(files=sorted(p.relative_to(context).as_posix() for p in context.rglob('*') if p.is_file()))
                Path(args[args.index('--iidfile') + 1]).write_text('sha256:' + 'c' * 64)
            return ''
        self.engine.docker = docker
        freeze_model(self.engine, self.workspace, self.deps, BASE)
        self.assertIn('app/server/main.py', seen['files'])
        self.assertIn('deps/py/lib.py', seen['files'])
        self.assertIn('Dockerfile', seen['files'])
        self.assertFalse([f for f in seen['files'] if '.git' in f.split('/')])

    def test_the_same_commit_gives_the_same_candidate(self):
        commit_task(self.workspace, 'task-1', '작업')
        self.assertEqual(freeze_model(self.engine, self.workspace, self.deps, BASE)['candidate_id'],
                         freeze_model(self.engine, self.workspace, self.deps, BASE)['candidate_id'])

    def test_uncommitted_changes_and_a_missing_or_bad_declaration_stop_the_freeze(self):
        commit_task(self.workspace, 'task-1', '작업')
        (self.workspace / 'server' / 'main.py').write_text('print(2)')          # changed after the last task commit
        with self.assertRaises(DomainError):
            freeze_model(self.engine, self.workspace, self.deps, BASE)
        commit_task(self.workspace, 'task-2', '작업')
        (self.workspace / APP_FILE).unlink()
        commit_task(self.workspace, 'task-3', '선언 삭제')
        with self.assertRaises(DomainError) as caught:
            freeze_model(self.engine, self.workspace, self.deps, BASE)
        self.assertIn(APP_FILE, caught.exception.message)
        (self.workspace / APP_FILE).write_text(json.dumps(dict(APP, start=['sh'])))
        commit_task(self.workspace, 'task-4', '나쁜 선언')
        with self.assertRaises(DomainError):
            freeze_model(self.engine, self.workspace, self.deps, BASE)

    def test_symlinks_in_the_workspace_refuse_the_freeze(self):
        os.symlink(self.root, self.workspace / 'link')
        with self.assertRaises(DomainError):
            freeze_model(self.engine, self.workspace, self.deps, BASE)


if __name__ == '__main__':
    unittest.main()
