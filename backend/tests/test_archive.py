"""Unsigned, read-only transfer checks. Synthetic reviews are not deployment evidence."""
import asyncio
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from jsonschema import ValidationError

from backend.api import create_app
from backend.config import Settings
from backend.archive import check, export_recording, import_recording, load_recording
from backend.contracts import ROOT, DomainError, canonical, digest
from backend.store import Store
from runner.review import Reviewer
import test_pipeline as fixtures


def seal(bundle):
    bundle['manifest_digest'] = digest({k: v for k, v in bundle.items() if k != 'manifest_digest'})
    return bundle


class ArchiveChecks(unittest.TestCase):
    setUp = fixtures.PipelineChecks.setUp
    live = fixtures.PipelineChecks.live
    planned = fixtures.PipelineChecks.planned
    command = fixtures.PipelineChecks.command
    post_command = fixtures.PipelineChecks.post_command
    approved = fixtures.PipelineChecks.approved
    built = fixtures.PipelineChecks.built
    validator = fixtures.PipelineChecks.validator

    def recording(self):
        snapshot = self.built()
        self.validator()
        with patch.object(Reviewer, 'security', return_value=dict(verdict='pass', checks={})):
            asyncio.run(self.worker.tick())
        return self.store.snapshot(snapshot['run_id'])

    def test_transfer_preserves_evidence_readonly_and_is_idempotent(self):
        source = self.recording()
        before = self.store.path.read_bytes()
        bundle = export_recording(self.store.path, source['run_id'])
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertNotIn('문의 목록을 만든다', canonical(bundle))
        context = next(a['content'] for a in bundle['artifacts'] if a['metadata']['kind'] == 'context')
        self.assertEqual(context['spec_version_id'], source['spec_version_id'])
        self.assertEqual(context['status'], 'ready')
        destination = Store(Path(self.temp.name) / 'keyless.sqlite3')
        result = import_recording(destination, bundle)
        replay = destination.snapshot(result['run_id'])
        self.assertEqual(replay['mode'], 'replay')
        self.assertEqual(replay['replay_source']['provenance'], 'imported_unsigned')
        self.assertEqual(destination.acceptance_status(replay['run_id']), self.store.acceptance_status(source['run_id']))
        self.assertEqual(import_recording(destination, bundle), result)
        recording = destination.replay_recordings()[0]
        self.assertEqual(recording['source_run_id'], replay['run_id'])
        self.assertEqual(recording['provenance'], 'imported_unsigned')
        clone = destination.create_run(result['project_id'], dict(mode='replay', source_run_id=replay['run_id']))
        self.assertEqual(clone['replay_source'], replay['replay_source'])
        self.assertEqual([e['occurred_at'] for e in destination.events(replay['run_id'], 0)], [e['occurred_at'] for e in bundle['events']])
        with self.assertRaises(DomainError) as blocked:
            destination.command(replay['run_id'], self.command(replay, 'pause'))
        self.assertEqual(blocked.exception.code, 'REPLAY_READ_ONLY')
        with destination.transaction() as db:
            for table in ('jobs', 'commands', 'grants', 'operations'):
                self.assertEqual(db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0], 0)

    def test_tampered_bundle_and_evidence_are_rejected(self):
        bundle = export_recording(self.store.path, self.planned()['run_id'])
        tampered = copy.deepcopy(bundle)
        tampered['snapshot']['state'] = 'succeeded'
        with self.assertRaises(DomainError):
            check(tampered)
        tampered = copy.deepcopy(bundle)
        tampered['artifacts'][0]['content'] = dict(forged='record')
        with self.assertRaises(DomainError):
            check(seal(tampered))

        tampered = copy.deepcopy(bundle)
        tampered['exporter']['contract_digests']['http.v1.schema.json'] = digest('old contract')
        with self.assertRaises(DomainError):
            check(seal(tampered))
        tampered = copy.deepcopy(bundle)
        tampered['project']['title'] = 'ghp_' + 'x' * 30
        with self.assertRaises(DomainError):
            check(seal(tampered))
        tampered['project']['title'] = '/Users/synthetic/private'
        with self.assertRaises(DomainError):
            check(seal(tampered))
        tampered = copy.deepcopy(bundle)
        content = dict(url='javascript:alert(1)', origin='javascript:alert(1)', commit_sha='a' * 40)
        metadata = dict(id='synthetic-unsafe-url', kind='preview', title='synthetic', content_digest=digest(content), public_summary='synthetic')
        tampered['snapshot']['artifacts'].append(metadata)
        tampered['artifacts'].append(dict(metadata=metadata, content=content))
        with self.assertRaises(DomainError):
            check(seal(tampered))

    def test_api_transfer_without_model_enforces_csrf_limits_and_readonly(self):
        source = self.built()
        exported = self.client.get(f"/api/runs/{source['run_id']}/recording")
        self.assertEqual(exported.status_code, 200, exported.text)
        bundle = exported.json()
        retrieval_ids = {a['metadata']['id'] for a in bundle['artifacts'] if a['metadata']['kind'] == 'retrieval'}
        self.assertTrue(retrieval_ids)
        invalid = copy.deepcopy(bundle)
        entry = next(a for a in invalid['artifacts'] if a['metadata']['kind'] == 'retrieval' and a['content']['sources'])
        entry['content']['sources'][0]['roles'] = ['unknown']
        entry['metadata']['content_digest'] = digest(entry['content'])
        next(a for a in invalid['snapshot']['artifacts'] if a['id'] == entry['metadata']['id'])['content_digest'] = entry['metadata']['content_digest']
        with self.assertRaises(ValidationError):
            check(seal(invalid))
        for kind in ('context', 'spec'):
            invalid = copy.deepcopy(bundle)
            entry = next(a for a in invalid['artifacts'] if a['metadata']['kind'] == kind)
            if kind == 'context':
                entry['content']['completed_fragments'] = entry['content']['total_fragments'] + 1
            else:
                entry['content']['repository'] = dict(url='https://user:password@example.org/app', branch='main')
            entry['metadata']['content_digest'] = digest(entry['content'])
            next(a for a in invalid['snapshot']['artifacts'] if a['id'] == entry['metadata']['id'])['content_digest'] = entry['metadata']['content_digest']
            with self.assertRaises(DomainError):
                check(seal(invalid))
        self.assertTrue(retrieval_ids.issubset({a for t in source['tasks'] for a in t['artifact_ids']}))
        self.assertTrue(retrieval_ids.issubset({a for e in bundle['events'] if e['event_type'] == 'retrieval_finished' for a in e['artifact_ids']}))
        destination = Store(Path(self.temp.name) / 'api-keyless.sqlite3')
        settings = Settings(destination.path, 'k' * 32)
        with TestClient(create_app(settings, destination), base_url='http://127.0.0.1:8016', client=('127.0.0.1', 12345)) as client:
            self.assertEqual(client.get('/api/replays').status_code, 401)
            session = client.post('/api/session', headers={'Origin': 'http://127.0.0.1:8016'}).json()
            headers = {'Origin': 'http://127.0.0.1:8016', 'X-CSRF-Token': session['csrf_token']}
            self.assertEqual(client.post('/api/recordings/import', json=bundle).status_code, 403)
            # Whitespace exercises the recording-only body limit without inventing record content.
            response = client.post('/api/recordings/import', content=' ' * 131073 + canonical(bundle), headers=headers)
            self.assertEqual(response.status_code, 200, response.text)
            run_id = response.json()['run_id']
            self.assertEqual(client.post('/api/recordings/import', json=bundle, headers=headers).json(), response.json())
            self.assertEqual(client.get('/api/replays').json()[0]['provenance'], 'imported_unsigned')
            replay = client.get(f'/api/runs/{run_id}').json()
            blocked = client.post(f'/api/runs/{run_id}/commands', json=self.command(replay, 'resume'), headers=headers)
            self.assertEqual(blocked.json()['error']['code'], 'REPLAY_READ_ONLY')
            self.assertEqual(client.get(f'/api/runs/{run_id}/recording').status_code, 200)
            self.assertEqual(client.post('/api/projects', content=' ' * 131073, headers=headers).status_code, 413)
            self.assertEqual(client.post('/api/recordings/import', content=b' ' * (16 * 1024 * 1024 + 1), headers=headers).status_code, 413)
            self.assertEqual(client.post('/api/recordings/import', content='{"version":1,"version":1}', headers=headers).status_code, 422)
        with destination.transaction() as db:
            for table in ('jobs', 'commands', 'grants', 'operations'):
                self.assertEqual(db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0], 0)

    def test_duplicate_json_keys_and_partial_import_do_not_overwrite(self):
        path = Path(self.temp.name) / 'bad.json'
        path.write_text('{"version":1,"version":2}')
        with self.assertRaises(DomainError):
            load_recording(path)
        bundle = export_recording(self.store.path, self.planned()['run_id'])
        destination = Store(Path(self.temp.name) / 'existing.sqlite3')
        existing = destination.project(dict(title='preserve', request='preserve'))
        row = bundle['artifacts'][0]
        old_run = destination.create_run(existing['project_id'], dict(mode='live'))
        with destination.transaction() as db:
            db.execute('INSERT INTO artifacts VALUES (?, ?, ?, ?, 0)', (row['metadata']['id'], old_run['run_id'], canonical(row['metadata']), canonical(row['content'])))
        with self.assertRaises(DomainError):
            import_recording(destination, bundle)
        self.assertEqual(destination.snapshot(old_run['run_id']), old_run)
        with destination.transaction() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM projects').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 1)

    def test_long_history_pages_and_transfer_preserve_all_event_ids(self):
        source = self.planned()
        with self.store.transaction() as db:
            for index in range(1200):
                self.store.save(db, source, 'warning', f'synthetic long-history fixture {index}', bump=False)
        events, cursor = [], 0
        while batch := self.store.events(source['run_id'], cursor):
            self.assertLessEqual(len(batch), 200)
            events.extend(batch)
            cursor = batch[-1]['seq']
        self.assertEqual(cursor, source['last_event_seq'])
        self.assertEqual([e['seq'] for e in events], list(range(1, cursor + 1)))
        bundle = export_recording(self.store.path, source['run_id'])
        self.assertEqual(bundle['events'], events)
        destination = Store(Path(self.temp.name) / 'long-history.sqlite3')
        result = import_recording(destination, bundle)
        cursor, imported = 0, []
        while batch := destination.events(result['run_id'], cursor):
            imported.extend(batch)
            cursor = batch[-1]['seq']
        self.assertEqual([e['event_id'] for e in imported], [e['event_id'] for e in events])
        self.assertEqual(export_recording(destination.path, result['run_id'])['recorded_at'], bundle['recorded_at'])

    def test_exported_source_copy_does_not_claim_parent_repository_revision(self):
        source = self.planned()
        package = Path(self.temp.name) / 'unversioned-package'
        package.mkdir()
        (package / 'docs').symlink_to(ROOT / 'docs', target_is_directory=True)
        with patch('backend.archive.ROOT', package), patch('backend.archive.subprocess.run') as git:
            bundle = export_recording(self.store.path, source['run_id'])
            git.assert_not_called()
        self.assertIsNone(bundle['exporter']['revision'])
        self.assertTrue(bundle['exporter']['dirty'])
