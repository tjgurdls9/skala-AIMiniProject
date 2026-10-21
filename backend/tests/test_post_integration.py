"""Developer fixtures only; no actual user approval, provider, location or deployment."""
import asyncio
from contextlib import closing
import importlib.util
import io
import json
import os
import runpy
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from backend.contracts import ROOT, SCHEMAS, DomainError, canonical, digest, validate
from jsonschema import Draft202012Validator, ValidationError
from runner.context import BUDGET, PlanningContext, plan_step_schema
import test_runtime as fixtures


class PostIntegrationChecks(unittest.TestCase):
    setUp = fixtures.RuntimeChecks.setUp
    command = fixtures.RuntimeChecks.command
    post_command = fixtures.RuntimeChecks.post_command

    def test_first_fragment_schema_cannot_invent_prior_requirement_revisions(self):
        proposal = dict(fixtures.PLAN, revisions=[dict(field='goal', previous_digest='sha256:'+'a'*64, quote='synthetic')])
        schema = SCHEMAS['http.v1.schema.json']['$defs']['PlanDraft']
        with self.assertRaises(ValidationError):
            Draft202012Validator(plan_step_schema(schema)).validate(proposal)
        proposal['revisions'] = []
        Draft202012Validator(plan_step_schema(schema)).validate(proposal)

    def test_followup_keeps_complete_plan_without_duplicating_prior_values(self):
        calls = []
        plan = dict(fixtures.PLAN, goal='x' * 4000)
        class Model(fixtures.FakeModel):
            async def generate(self, packet, schema):
                calls.append(packet)
                return dict(plan)
        self.worker.model = Model()
        self.worker.heartbeat()
        project = self.store.project(dict(title='synthetic bounded context', request='x' * 2401))
        self.store.create_run(project['project_id'], dict(mode='live'))
        job = self.worker.claim()
        documents = [dict(text='r' * 3800)]
        job['packet']['retrieved_documents'] = documents
        result = asyncio.run(PlanningContext(self.store).plan(job, self.worker, SCHEMAS['http.v1.schema.json']['$defs']['PlanDraft']))
        self.assertEqual(result, plan)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1]['accumulated_plan'], plan)
        self.assertEqual(calls[1]['retrieved_documents'], documents)
        self.assertEqual(calls[1]['prior_values']['goal'], [digest(plan['goal'])])
        self.assertTrue(all(len(canonical(call).encode()) <= BUDGET for call in calls))

    def test_support_is_per_plan_frozen_and_blocks_approve_without_mutation(self):
        self.worker.heartbeat()
        request = '합성 개발 요청: 내 위치 주변 카페 추천과 지도 검색'
        project = self.store.project(dict(title='synthetic cafemap', request=request))
        source = self.store.create_run(project['project_id'], dict(mode='live'), 'cafemap-v1')
        asyncio.run(self.worker.tick())
        snapshot = self.store.snapshot(source['run_id'])
        self.assertEqual(snapshot['state'], 'awaiting_plan_approval')
        metadata = next(a for a in snapshot['artifacts'] if a['kind'] == 'spec')
        plan = self.store.read_artifact(metadata['id'])
        support = plan['support']
        validate('PlanSupport', support)
        self.assertEqual(support['spec_version_id'], snapshot['spec_version_id'])
        self.assertEqual(support['unsupported'][0]['request_quote'], request)
        self.assertFalse(support['implementation_allowed'])
        self.assertEqual(support['external'][0]['status'], 'unconfirmed')
        self.assertEqual(support['external'][0]['provider'], 'geoapify')
        planner = next(t for t in snapshot['tasks'] if t['role'] == 'planner')
        self.assertEqual({a['kind'] for a in snapshot['artifacts'] if a['id'] in planner['artifact_ids']}, {'spec','context','retrieval'})
        approval = snapshot['approvals'][-1]
        blocked = self.post_command(self.command(snapshot, 'decide', dict(approval_id=approval['id'], target_digest=approval['target_digest'], decision='approve')))
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.json()['error']['code'], 'INVALID_STATE')
        self.assertEqual(self.store.snapshot(source['run_id']), snapshot)
        with self.store.transaction() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM commands').fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM jobs WHERE role='builder'").fetchone()[0], 0)
        replay = self.store.create_run(project['project_id'], dict(mode='replay', source_run_id=source['run_id']))
        self.assertEqual(self.store.read_artifact(next(a['id'] for a in replay['artifacts'] if a['kind'] == 'spec'))['support'], support)
        with self.assertRaises(sqlite3.IntegrityError), self.store.transaction() as db:
            db.execute("UPDATE run_templates SET template_id='requests-v1' WHERE run_id=?", (source['run_id'],))
        with self.assertRaises(DomainError):
            self.store.create_run(project['project_id'], dict(mode='live'), '../escape')

    def test_unconfigured_release_get_is_readonly_and_contract_valid(self):
        self.worker.heartbeat()
        project = self.store.project(dict(title='synthetic', request='synthetic'))
        run = self.store.create_run(project['project_id'], dict(mode='live'))
        response = self.client.get(f"/api/runs/{run['run_id']}/release")
        self.assertEqual(response.status_code, 200)
        validate('ReleaseView', response.json())
        self.assertEqual(response.json()['state'], 'unconfigured')
        self.assertFalse(response.json()['enabled'])
        self.assertIsNone(response.json()['target'])
        self.assertEqual(response.json()['operations'], [])
        self.assertEqual(self.store.snapshot(run['run_id']), run)

    def test_cafemap_profile_has_no_fake_places_or_coordinate_storage(self):
        workspace = self.worker.pipeline.engine.workspace('1' * 32, '2' * 32, 'cafemap-v1')
        self.assertTrue((workspace/'app_frontend/vendor/vue.esm-browser.prod.js').is_file())
        before = Path.cwd()
        os.chdir(workspace)
        try:
            spec = importlib.util.spec_from_file_location('synthetic_cafemap', workspace/'app_backend/main.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.DATABASE = Path(self.temp.name)/'preferences.sqlite3'
            with TestClient(module.app) as client:
                self.assertEqual(client.get('/health').json(), dict(status='ok'))
                self.assertEqual(client.get('/api/map/source').json()['status'], 'unconfigured')
                blocked = client.post('/api/map/search', json=dict(latitude=37.5, longitude=127, external_consent=False))
                self.assertEqual(blocked.status_code, 503)
                self.assertEqual(blocked.json()['error']['code'], 'PROVIDER_UNCONFIGURED')
                self.assertEqual(client.post('/api/map/search', json=dict(latitude=91, longitude=127)).status_code, 422)
                self.assertEqual(client.post('/api/preferences', json=dict(radius_m=2000, internet_only=True)).status_code, 200)
                self.assertEqual(client.get('/api/preferences').json(), dict(radius_m=2000, internet_only=True))
                self.assertEqual(client.post('/api/preferences', json=dict(radius_m=2000, latitude=37.5)).status_code, 422)
            with closing(sqlite3.connect(module.DATABASE)) as db:
                self.assertEqual([r[1] for r in db.execute('PRAGMA table_info(preferences)')], ['id','radius_m','internet_only'])
        finally:
            os.chdir(before)

    def test_trusted_proxy_blocks_candidate_provider_routes_without_network(self):
        opener = MagicMock()
        with patch('sys.argv', ['preview.py','candidate:8080','cafemap-v1']), patch('http.server.ThreadingHTTPServer'), patch('urllib.request.build_opener', return_value=opener):
            namespace = runpy.run_path(str(ROOT/'infra/checks/preview.py'))
        handler = namespace['Proxy'].__new__(namespace['Proxy'])
        handler.command, handler.path = 'POST', '/api/map/search'
        handler.request_version = 'HTTP/1.1'
        handler._headers_buffer = []
        handler.headers = {'Content-Length':'2'}
        handler.rfile, handler.wfile = io.BytesIO(b'{}'), io.BytesIO()
        statuses, headers = [], []
        handler.send_response = statuses.append
        handler.send_header = lambda key,value: headers.append((key,value))
        handler.handle_request()
        self.assertEqual(statuses, [503])
        self.assertEqual(json.loads(handler.wfile.getvalue().strip())['error']['code'], 'PROVIDER_UNCONFIGURED')
        self.assertTrue(any(k == 'Permissions-Policy' and 'geolocation=()' in v for k,v in headers))
        opener.open.assert_not_called()
