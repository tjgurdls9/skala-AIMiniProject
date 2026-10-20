import asyncio
import os
from pathlib import Path
import sys
import tempfile
import unittest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from backend.contracts import DomainError
from backend.store import Store
from knowledge import Corpus
from runner.access import RoleScope, issue_grant
from runner.worker import Worker
import test_runtime as fixtures


class AccessChecks(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(tempfile.TemporaryDirectory())
        self.store = Store(Path(self.temp) / "state.sqlite3")
        self.worker = Worker(self.store, fixtures.FakeModel())
        self.worker.heartbeat()
        project = self.store.project({"title": "synthetic", "request": "make a tiny app"})
        self.run = self.store.create_run(project["project_id"], {"mode": "live"})
        self.job = self.worker.claim()
        self.token = issue_grant(self.store, self.job)
        self.scope = RoleScope(self.store, self.token)

    def test_role_acl_filters_before_ranking(self):
        corpus = Corpus(self.store)
        self.assertNotIn("knowledge/validation.md", {r["path"] for r in corpus.search("builder", "Validation role")})
        self.assertIn("knowledge/validation.md", {r["path"] for r in corpus.search("validator", "Validation role")})
        self.assertNotIn("knowledge/security.md", {r["path"] for r in corpus.search("validator", "Security role")})
        with self.assertRaises(DomainError):
            self.scope.resource("events")
        with self.assertRaises(DomainError):
            self.scope.patch("app_backend/main.py", "x", None)

    def test_capability_revoked_by_pause(self):
        command = fixtures.RuntimeChecks.command(self, self.run, "pause")
        self.store.command(self.run["run_id"], command)
        with self.assertRaises(DomainError):
            self.scope.resource("contract")

    def test_real_stdio_mcp_handshake_and_tools(self):
        async def check():
            env = {"PATH": os.defpath, "LIFECYCLE_DB": str(self.store.path), "LIFECYCLE_GRANT": self.token}
            params = StdioServerParameters(command=sys.executable, args=["-m", "runner.mcp_server"], env=env)
            async with stdio_client(params) as streams, ClientSession(*streams) as session:
                await session.initialize()
                names = {t.name for t in (await session.list_tools()).tools}
                self.assertEqual(names, {"search_documents"})
                resource = await session.read_resource("lifecycle://contract")
                self.assertTrue(resource.contents)
                denied = await session.call_tool("patch_file", {"path": "../../private"})
                self.assertTrue(denied.isError)
                result = await session.call_tool("search_documents", {"query": "SSE"})
                self.assertFalse(result.isError)
        asyncio.run(check())

    def test_path_traversal_symlink_and_digest_conflict(self):
        self.worker.finish(self.job, fixtures.PLAN)
        snapshot = self.store.snapshot(self.run["run_id"])
        approval = snapshot["approvals"][-1]
        command = fixtures.RuntimeChecks.command(self, snapshot, "decide", {"approval_id": approval["id"], "target_digest": approval["target_digest"], "decision": "approve"})
        self.store.command(snapshot["run_id"], command)
        job = self.worker.claim()
        scope = RoleScope(self.store, issue_grant(self.store, job, self.temp))
        created = scope.patch("app_backend/main.py", "print('safe')", None)
        with self.assertRaises(DomainError):
            scope.patch("app_backend/main.py", "changed", None)
        scope.patch("app_backend/main.py", "changed", created["content_digest"])
        for path in ("../private", "/etc/passwd", "app_backend/../../secret", "app_backend/.env", "reviews/result.json"):
            with self.assertRaises(DomainError):
                scope.read(path)
        (Path(self.temp) / "app_backend/link.py").symlink_to(Path(self.temp) / "state.sqlite3")
        with self.assertRaises(DomainError):
            scope.read("app_backend/link.py")
