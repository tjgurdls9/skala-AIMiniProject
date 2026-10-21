"""Review H-5: nothing a sandboxed program writes or prints may grow the host worker's memory or disk without bound."""
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.contracts import DomainError
from runner.commands import CAPTURE_BYTES, DockerExecutor, bounded_run
from runner.pipeline import Pipeline
from runner.workspace import MAX_FILE_BYTES, MAX_WORKSPACE_BYTES, Workspace

IMAGE = 'python@sha256:' + 'a' * 64


def never_read_whole(self, *args, **kwargs):
    raise AssertionError('an oversized file was read into memory')


class BoundedRun(unittest.TestCase):
    def test_runaway_output_is_kept_to_the_capture_limit(self):
        done = bounded_run([sys.executable, '-c', "import sys; sys.stdout.write('x' * 20_000_000); sys.stderr.write('e' * 20_000_000)"], timeout=60)
        self.assertEqual((done.returncode, len(done.stdout), len(done.stderr)), (0, CAPTURE_BYTES + 1, CAPTURE_BYTES + 1))

    def test_normal_output_is_returned_whole(self):
        done = bounded_run([sys.executable, '-c', "print('hello'); import sys; sys.exit(3)"], timeout=60)
        self.assertEqual((done.returncode, done.stdout.strip()), (3, b'hello'))

    def test_a_program_that_outlives_the_timeout_is_stopped_and_reported(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            bounded_run([sys.executable, '-c', 'import time; time.sleep(30)'], timeout=0.5)

    def test_the_executor_marks_output_over_the_limit_as_truncated_without_keeping_it_all(self):
        executor = DockerExecutor(IMAGE, runner=lambda args, **kw: subprocess.CompletedProcess(args, 0, b'x' * (CAPTURE_BYTES + 1), b''))
        result = executor.run(Path('/tmp'), ['python', '-c', 'pass'], '.', 5)
        self.assertTrue(result.truncated)

    def test_a_single_file_a_container_writes_is_capped(self):
        args = DockerExecutor(IMAGE).build_args('n', Path('/tmp/w'), ['python', '-c', 'pass'], '.', 'none', None, None, False)
        self.assertTrue(any(a.startswith('fsize=') for a in args[args.index('--ulimit') + 1:args.index('--ulimit') + 2]))


class WorkspaceReads(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (self.root / 'big.txt').write_text('x' * (MAX_FILE_BYTES + 1))
        (self.root / 'small.txt').write_text('ok')
        self.workspace = Workspace(self.root)

    def test_listing_does_not_read_a_file_over_the_size_limit(self):
        real = Path.read_text

        def guarded(path, *args, **kwargs):
            if path.name == 'big.txt':
                never_read_whole(path)
            return real(path, *args, **kwargs)
        with patch.object(Path, 'read_text', guarded):
            listed = {f['path']: f['content_digest'] for f in self.workspace.list_files()}
        self.assertIsNone(listed['big.txt'])
        self.assertIsNotNone(listed['small.txt'])

    def test_the_manifest_hashes_files_in_chunks(self):
        with patch.object(Path, 'read_bytes', never_read_whole):
            manifest = self.workspace.manifest()
        self.assertEqual(sorted(manifest), ['big.txt', 'small.txt'])

    def test_the_before_after_tree_marks_an_oversized_file_by_its_hash_instead_of_loading_it(self):
        real = Path.read_text

        def guarded(path, *args, **kwargs):
            if path.name == 'big.txt':
                never_read_whole(path)
            return real(path, *args, **kwargs)
        with patch.object(Path, 'read_text', guarded):
            tree = Pipeline.read_tree(self.root)
        self.assertEqual(tree['small.txt'], 'ok')
        self.assertTrue(tree['big.txt'].startswith('[oversized file sha256:'))


class WorkspaceSize(unittest.TestCase):
    def test_a_workspace_over_the_total_limit_is_reported(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (root / 'a.bin').write_bytes(b'0' * 2048)
        workspace = Workspace(root)
        self.assertLess(workspace.total_bytes(), MAX_WORKSPACE_BYTES)
        with patch('runner.workspace.MAX_WORKSPACE_BYTES', 1024), self.assertRaises(DomainError) as refused:
            workspace.require_room()
        self.assertEqual(refused.exception.code, 'INVALID_COMMAND')


if __name__ == '__main__':
    unittest.main()
