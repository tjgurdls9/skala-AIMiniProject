"""Context/semantic boundaries with explicit synthetic model vectors and tool results."""
import asyncio
import copy
import json
import unittest
import unittest.mock
from unittest.mock import patch

from backend.contracts import DomainError, canonical, digest, validate
from knowledge import Corpus
from runner.model import ModelUnavailable, inference_slot
import test_runtime


class SystemPromptChecks(unittest.TestCase):
    def test_each_role_has_wording_that_matches_its_authority(self):
        from runner.model import system_prompt
        prompts = {role: system_prompt(dict(role=role)) for role in ('planner', 'builder', 'validator', 'security')}
        self.assertEqual(len(set(prompts.values())), 4)
        self.assertEqual(system_prompt(dict(role='builder', step='act')), prompts['builder'])
        self.assertEqual(system_prompt(dict(role='unknown')), prompts['planner'])
        self.assertNotIn('execute tools', prompts['builder'])         # the builder only proposes; the server runs the tools
        self.assertIn('You only propose', prompts['builder'])
        for role in ('planner', 'validator', 'security'):
            self.assertIn('Never approve', prompts[role])
        self.assertIn('Never modify code', prompts['validator'])
        self.assertIn('Never modify code', prompts['security'])
        self.assertNotIn('Never modify code', prompts['planner'])


class ThinkFlagChecks(unittest.IsolatedAsyncioTestCase):
    async def sent(self, **kwargs):
        from runner import model as module
        captured = {}

        class Client:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url):
                class Response:
                    def raise_for_status(self):
                        pass

                    def json(self):
                        return {'models': [{'name': 'qwen3.5:4b'}]} if url.endswith('/api/tags') else {'models': []}
                return Response()

            async def post(self, url, json):
                captured.update(json)

                class Response:
                    status_code = 200

                    def raise_for_status(self):
                        pass

                    def json(self):
                        return {'message': {'content': '{"tool": "finish", "summary": "x"}'}}
                return Response()
        with unittest.mock.patch.object(module.httpx, 'AsyncClient', Client):
            await module.Ollama('qwen3.5:4b', **kwargs).generate(dict(role='builder', step='act'), {})
        return captured

    async def test_thinking_is_off_by_default_and_can_be_switched_on_for_comparison(self):
        self.assertIs((await self.sent())['think'], False)
        self.assertIs((await self.sent(think=True))['think'], True)
        self.assertEqual((await self.sent(think=True))['options']['temperature'], 0)


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
        context = next(a for a in snapshot['artifacts'] if a['kind'] == 'context')
        evidence = self.store.read_artifact(context['id'])
        self.assertEqual(evidence['status'], 'needs_input')
        self.assertEqual(evidence['completed_fragments'], 1)
        self.assertNotIn(raw, canonical(evidence))

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

