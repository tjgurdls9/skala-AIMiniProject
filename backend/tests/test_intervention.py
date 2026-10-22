"""F6: workspace changes that no ledgered tool call explains mark the run as intervened (R30: a developer's edit is not the model's work)."""
import asyncio
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runner.candidate import commit_task, workspace_state
from runner.intervention import ledgered_paths, unledgered
from runner.pipeline import Pipeline
import test_pipeline as pipeline


def call(tool, ok=True, **args):
    return dict(tool=tool, ok=ok, args=args)


class LedgerRules(unittest.TestCase):
    def test_only_successful_file_mutations_explain_a_changed_path(self):
        calls = [call("write_file", path="a.py"), call("write_file", ok=False, path="refused.py"), call("delete_file", path="old.py"),
                 call("move_file", source="x.py", target="y.py"), call("read_file", path="read.py")]
        self.assertEqual(ledgered_paths(calls), {"a.py", "old.py", "x.py", "y.py"})

    def test_a_changed_path_with_no_ledger_entry_is_unexplained(self):
        calls = [call("write_file", path="a.py")]
        self.assertEqual(unledgered(["a.py", "b.py", "c.py"], calls), ["b.py", "c.py"])
        self.assertEqual(unledgered(["a.py"], calls), [])

    def test_commands_do_not_explain_changes_because_they_cannot_write_the_workspace(self):
        calls = [call("write_file", path="a.py"), call("run_tests", argv=["pytest"])]
        self.assertEqual(unledgered(["a.py", "generated.txt"], calls), ["generated.txt"])


class InstallLockFiles(unittest.TestCase):
    """Re-review N-3: the lock file a successful install writes through the ledgered install tool is not a hand edit."""
    def test_a_successful_install_explains_its_own_lock_file_only(self):
        pip = [call("install_dependencies", manager="pip", packages=["fastapi"])]
        self.assertEqual(unledgered(["requirements.lock", "package-lock.json", "a.py"], pip), ["a.py", "package-lock.json"])
        npm = [call("install_dependencies", manager="npm", packages=["left-pad"])]
        self.assertEqual(unledgered(["requirements.lock", "package-lock.json"], npm), ["requirements.lock"])

    def test_a_failed_install_explains_nothing(self):
        failed = [call("install_dependencies", ok=False, manager="pip", packages=["fastapi"])]
        self.assertEqual(unledgered(["requirements.lock"], failed), ["requirements.lock"])


class WorkspaceState(unittest.TestCase):
    def setUp(self):
        self.workspace = Path(self.enterContext(tempfile.TemporaryDirectory())) / "ws"
        self.workspace.mkdir()

    def test_a_committed_workspace_is_clean_and_reports_its_head(self):
        (self.workspace / "a.py").write_text("x")
        head = commit_task(self.workspace, "t1", "첫 작업")
        self.assertEqual(workspace_state(self.workspace), (head, []))

    def test_edits_after_the_commit_are_listed_by_path(self):
        (self.workspace / "a.py").write_text("x")
        (self.workspace / "gone.py").write_text("x")
        commit_task(self.workspace, "t1", "첫 작업")
        (self.workspace / "a.py").write_text("changed")
        (self.workspace / "gone.py").unlink()
        (self.workspace / "한글.py").write_text("new")
        self.assertEqual(workspace_state(self.workspace)[1], ["a.py", "gone.py", "한글.py"])

    def test_a_workspace_without_history_has_no_head(self):
        self.assertEqual(workspace_state(self.workspace), (None, []))


class InterventionMarking(unittest.TestCase):
    def setUp(self):
        pipeline.PipelineChecks.setUp(self)

    live = pipeline.PipelineChecks.live
    planned = pipeline.PipelineChecks.planned
    command = pipeline.PipelineChecks.command
    post_command = pipeline.PipelineChecks.post_command
    approved = pipeline.PipelineChecks.approved

    def run_task(self, files, ledgered, commands=False, between=None):
        """Run the next builder task; `files` are written to the workspace, `ledgered` of them also get a tool-ledger entry."""
        job = self.worker.claim()
        task_id = job["packet"]["options"]["task_id"]
        workspace = self.worker.pipeline.engine.workspace(job["run_id"], job["packet"]["spec_version_id"], "blank-v1")
        if between:
            between(workspace)

        async def edit(pipeline_self, job, worker, workspace):
            for path, text in files.items():
                (workspace / path).parent.mkdir(parents=True, exist_ok=True)
                (workspace / path).write_text(text)
            for path in ledgered:
                self.store.record_tool_call(dict(run_id=job["run_id"], job_id=job["id"], attempt_id=job["attempt_id"], task_id=task_id,
                                                 role="builder", tool="write_file", args=dict(path=path), ok=True))
            if commands:
                self.store.record_tool_call(dict(run_id=job["run_id"], job_id=job["id"], attempt_id=job["attempt_id"], task_id=task_id,
                                                 role="builder", tool="run_tests", args=dict(argv=["pytest"]), ok=True))
        candidate = dict(commit_sha="a" * 40, image_digest="sha256:" + "b" * 64, manifest={}, path=str(workspace), app=dict(runtime="python", health="/health"))
        with patch.object(Pipeline, "model_edit", new=edit), patch("runner.pipeline.freeze_model", return_value=candidate):   # the last task freezes
            asyncio.run(self.worker.pipeline.build(job, self.worker))
        return self.store.snapshot(job["run_id"]), task_id

    def interventions(self, snapshot):
        return self.store.interventions(snapshot["run_id"])

    def test_a_task_whose_every_change_is_ledgered_leaves_no_mark(self):
        snapshot = self.approved()
        after, _ = self.run_task({"server/a.py": "x"}, ["server/a.py"])
        self.assertEqual(self.interventions(after), [])
        self.assertFalse(any(e["event_type"] == "warning" for e in self.store.events(after["run_id"], 0)))

    def test_a_file_the_ledger_does_not_explain_marks_the_run(self):
        self.approved()
        after, task_id = self.run_task({"server/a.py": "x", "server/sneaky.py": "y"}, ["server/a.py"])
        self.assertEqual(self.interventions(after), [dict(task_id=task_id, kind="outside_ledger", paths=["server/sneaky.py"])])
        warning = [e for e in self.store.events(after["run_id"], 0) if e["event_type"] == "warning"]
        self.assertEqual(len(warning), 1)
        self.assertIn("원장", warning[0]["summary"])

    def test_the_mark_does_not_stop_the_run(self):
        self.approved()
        after, _ = self.run_task({"server/sneaky.py": "y"}, [])
        task = next(t for t in after["tasks"] if t["state"] == "succeeded" and t["role"] == "builder")
        self.assertEqual(task["work_kind"], "backend")
        self.assertEqual(self.worker.claim()["packet"]["options"]["task_kind"], "frontend")

    def test_an_edit_made_between_two_tasks_is_marked_on_the_next_task(self):
        self.approved()
        self.run_task({"server/a.py": "x"}, ["server/a.py"])
        after, task_id = self.run_task({"web/b.js": "z"}, ["web/b.js"], between=lambda ws: (ws / "server/a.py").write_text("hand edit"))
        self.assertEqual(self.interventions(after), [dict(task_id=task_id, kind="edited_between_tasks", paths=["server/a.py"])])

    def test_history_rewritten_between_two_tasks_is_marked(self):
        self.approved()
        self.run_task({"server/a.py": "x"}, ["server/a.py"])

        def commit_by_hand(ws):
            (ws / "hand.py").write_text("h")
            git = ["git", "--git-dir", str(ws) + ".git", "--work-tree", str(ws), "-c", "user.name=dev", "-c", "user.email=d@d"]
            subprocess.run([*git, "add", "-A"], check=True, capture_output=True)
            subprocess.run([*git, "commit", "-q", "-m", "by hand"], check=True, capture_output=True)
        after, task_id = self.run_task({"web/b.js": "z"}, ["web/b.js"], between=commit_by_hand)
        self.assertEqual(self.interventions(after), [dict(task_id=task_id, kind="history_changed", paths=[])])

    def test_a_file_made_during_a_task_that_ran_commands_is_still_marked(self):
        self.approved()
        after, task_id = self.run_task({"server/a.py": "x", ".pytest_cache/README": "cache"}, ["server/a.py"], commands=True)
        self.assertEqual(self.interventions(after), [dict(task_id=task_id, kind="outside_ledger", paths=[".pytest_cache/README"])])


if __name__ == "__main__":
    unittest.main()
