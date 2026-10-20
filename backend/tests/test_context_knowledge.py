"""Context/semantic boundaries with explicit synthetic model vectors and tool results."""
import asyncio
import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.contracts import DomainError, canonical, digest, validate
from knowledge import Corpus
from runner.access import RoleScope, issue_grant
from runner.context import implement
from runner.model import ModelUnavailable, inference_slot
from runner.sandbox import PATCH_SCHEMA
import test_pipeline
import test_runtime


class ContextChecks(unittest.TestCase):
    setUp = test_pipeline.PipelineChecks.setUp
    live = test_pipeline.PipelineChecks.live
    planned = test_pipeline.PipelineChecks.planned
    command = test_pipeline.PipelineChecks.command
    post_command = test_pipeline.PipelineChecks.post_command
    approved = test_pipeline.PipelineChecks.approved
    def test_patch_response_loss_is_reconciled_without_regeneration(self):
        snapshot = self.approved()
        job = self.worker.claim()
        path = 'app_frontend/style.css'
        workspace = self.worker.pipeline.engine.workspace(job['run_id'], snapshot['spec_version_id'])
        scope = RoleScope(self.store, issue_grant(self.store, job, workspace))
        original = scope.read(path)
        content = original['content'] + '\n/* synthetic recovery */'
        calls = []
        class Session:
            lost = True
            async def call_tool(self, name, args):
                result = scope.patch(args['path'], args['content'], args['expected_digest'])
                if self.lost:
                    self.lost = False
                    raise ModelUnavailable('synthetic lost acknowledgement')
                return SimpleNamespace(isError=False, content=[SimpleNamespace(text=json.dumps(result))])
        session = Session()
        async def output(job, packet, schema):
            calls.append(packet)
            return dict(summary='synthetic', files=[dict(path=path, content=content)])
        with patch.object(self.worker, 'infer', side_effect=output):
            with self.assertRaises(ModelUnavailable):
                asyncio.run(implement(self.store, session, job, self.worker, [original], [], [path], PATCH_SCHEMA))
            self.assertEqual(scope.read(path)['content'], content)
            asyncio.run(implement(self.store, session, job, self.worker, [scope.read(path)], [], [path], PATCH_SCHEMA))
        self.assertEqual(len(calls), 1)
        self.assertEqual(scope.read(path)['content'].count('synthetic recovery'), 1)
        self.assertEqual(calls[0]['approved_spec']['acceptance'], test_runtime.PLAN['acceptance'])


class KnowledgeChecks(unittest.TestCase):
    setUp = test_runtime.RuntimeChecks.setUp
    def test_mandatory_overflow_requests_input_without_trimming(self):
        class Large(test_runtime.FakeModel):
            async def generate(self, packet, schema):
                plan = copy.deepcopy(test_runtime.PLAN)
                plan['constraints'] = ['가' * 5000]
                return plan
        self.worker.model = Large()
        self.worker.heartbeat()
        raw = '원문 유지 ' * 500
        project = self.store.project(dict(title='synthetic', request=raw))
        run = self.store.create_run(project['project_id'], dict(mode='live'))
        asyncio.run(self.worker.tick())
        snapshot = self.store.snapshot(run['run_id'])
        self.assertEqual(snapshot['state'], 'needs_input')
        self.assertFalse(snapshot['approvals'])
        with self.store.transaction() as db:
            self.assertEqual(db.execute('SELECT content FROM requests').fetchone()[0], raw)
            private = json.loads(db.execute("SELECT content FROM artifacts WHERE public=0 AND json_extract(metadata,'$.kind')='context'").fetchone()[0])
        self.assertEqual(private['status'], 'needs_input')
        self.assertEqual(private['completed_fragments'], 1)

    def test_version_conflict_is_search_error(self):
        Corpus(self.store)
        with self.store.transaction() as db:
            row = db.execute("SELECT * FROM knowledge WHERE json_extract(metadata,'$.path')='knowledge/sandbox.md'").fetchone()
            metadata = json.loads(row['metadata'])
            metadata['content_digest'] = digest('synthetic different source')
            db.execute('INSERT INTO knowledge VALUES (?, ?, ?)', (digest('synthetic-conflict'), canonical(metadata), 'synthetic different source'))
        result = asyncio.run(Corpus(self.store).retrieve('builder', 'read-only'))
        self.assertEqual(result['evidence']['status'], 'search_error')
        self.assertEqual(result['evidence']['error_code'], 'VERSION_CONFLICT')
        self.assertFalse(result['documents'])
    def test_semantic_acl_cache_provenance_and_unavailable(self):
        corpus = Corpus(self.store)
        first = corpus.search('validator', 'Validation role')[0]
        self.assertEqual(Corpus(self.store).search('validator', 'Validation role')[0]['collected_at'], first['collected_at'])
        class Embedding:
            calls = []
            async def embedding_identity(self):
                return 'synthetic-embedding@sha256:' + 'a' * 64
            async def embed(self, texts):
                self.calls.append(texts)
                return [[1., 0.] for _ in texts]
        model = Embedding()
        result = asyncio.run(corpus.retrieve('builder', '호스트비밀보호', model))
        self.assertFalse(corpus.search('builder', '호스트비밀보호'))
        self.assertEqual(result['evidence']['method'], 'semantic')
        self.assertEqual(result['evidence']['status'], 'found')
        validate('RetrievalEvidence', result['evidence'])
        self.assertTrue(all('builder' in r['roles'] for r in result['documents']))
        self.assertFalse(any('Validation role' in text or 'Security role' in text for batch in model.calls for text in batch))
        model.calls.clear()
        asyncio.run(corpus.retrieve('builder', '호스트비밀보호', model))
        self.assertEqual(len(model.calls), 1)  # Only query embedding remains.
        with patch.object(model, 'embed', side_effect=ModelUnavailable()):
            failed = asyncio.run(corpus.retrieve('builder', '호스트비밀보호', model))
        self.assertEqual(failed['evidence']['status'], 'search_error')
        self.assertFalse(failed['documents'])
        self.assertEqual(asyncio.run(corpus.retrieve('builder', '없는단어결합'))['evidence']['status'], 'no_results')
        with self.assertRaises(DomainError):
            asyncio.run(corpus.retrieve('release', 'x', model))

    def test_cross_client_inference_slot_and_cancelled_waiter(self):
        async def exercise():
            calls = []
            async def use(value):
                async with inference_slot():
                    calls.append(('start', value))
                    await asyncio.sleep(.15)
                    calls.append(('end', value))
            await asyncio.gather(use(1), use(2))
            self.assertEqual(calls, [('start', 1), ('end', 1), ('start', 2), ('end', 2)])
            async with inference_slot():
                waiter = asyncio.create_task(use(3))
                await asyncio.sleep(.01)
                waiter.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await waiter
            await use(4)
        asyncio.run(exercise())

