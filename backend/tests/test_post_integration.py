"""Developer fixtures only; no actual user approval, provider, location or deployment."""
import asyncio
import json
import sqlite3
import unittest

from backend.contracts import SCHEMAS, DomainError, canonical, digest, validate
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

    def test_a_run_keeps_its_template_and_unknown_templates_are_refused(self):
        project = self.store.project(dict(title='synthetic', request='합성 개발 요청'))
        run = self.store.create_run(project['project_id'], dict(mode='live'), 'blank-v1')
        with self.assertRaises(sqlite3.IntegrityError), self.store.transaction() as db:
            db.execute("UPDATE run_templates SET template_id='requests-v1' WHERE run_id=?", (run['run_id'],))
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
