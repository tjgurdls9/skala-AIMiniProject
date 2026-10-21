"""Synthetic approval fixtures/mock external adapters; no actual push, deploy or HITL."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import ANY, patch

from backend.contracts import ROOT, DomainError, canonical, digest, plan_inputs, validate
from backend.archive import check, export_recording
from backend.store import Store, now, uid
from runner.model import ModelUnavailable
from runner.release import ReleaseOperations
from runner.worker import POLICY
import test_runtime


class ReleaseChecks(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(tempfile.TemporaryDirectory())
        self.store = Store(Path(self.temp) / 'state.sqlite3')
        project = self.store.project(dict(title='synthetic release fixture', request='synthetic'))
        self.snapshot = self.store.create_run(project['project_id'], dict(mode='live'))
        self.repository = dict(url='https://github.com/test/generated.git', branch='generated/fixture', auto_deploy=False)
        self.environment = dict(id='synthetic-local', label='synthetic', provider='docker_local', exposure='local', port=49101,
                                free_verified=True, free_evidence='synthetic fixture; not real verification')
        self.local, self.remote = 'sha256:' + 'b' * 64, 'sha256:' + 'c' * 64
        spec_id = uid()
        package = dict(copy.deepcopy(test_runtime.PLAN), spec_version_id=spec_id, stack=['FastAPI', 'Vue 3', 'SQLite'],
                       repository={k: self.repository[k] for k in ('url', 'branch')}, deployment={k: self.environment[k] for k in ('id', 'label', 'exposure')},
                       free_policy=POLICY, allowed_tools=['read_file'], contract_digests=plan_inputs('blank-v1'))
        candidate = dict(commit_sha='a' * 40, image_digest=self.local, path=str(Path(self.temp) / 'candidate'), manifest={})
        Path(candidate['path']).mkdir()
        with self.store.transaction() as db:
            self.snapshot.update(spec_version_id=spec_id, state='preview_ready')
            db.execute('INSERT INTO specs VALUES (?, ?, ?, ?)', (spec_id, self.snapshot['run_id'], canonical(package), now()))
            self.store.artifact(db, self.snapshot, 'spec', 'synthetic spec', package)
            for role in ('validator', 'security'):
                body = dict(role=role, spec_version_id=spec_id, commit_sha=candidate['commit_sha'], image_digest=self.local, verdict='pass')
                artifact = self.store.artifact(db, self.snapshot, 'test_result' if role == 'validator' else 'security_result', 'synthetic report', body)
                self.snapshot['reports'].append(dict(body, id=uid(), artifact_id=artifact['id'], content_digest=artifact['content_digest']))
            plan_target = dict(gate='plan', spec_version_id=spec_id, plan_digest=digest(package))
            self.snapshot['approvals'].append(dict(id=uid(), target=plan_target, target_digest=digest(plan_target), state='approved'))
            db.execute('INSERT INTO candidates VALUES (?, ?, ?, ?)', (uid(), self.snapshot['run_id'], spec_id, canonical(candidate)))
            self.store.save(db, self.snapshot, 'warning', 'synthetic fixture, not a real review or approval')
        self.operations = ReleaseOperations(self.store, current=lambda db: True)
        with patch.object(self.operations.engine, 'runtime', return_value=self.local), patch.object(self.operations.engine, 'docker', side_effect=[json.dumps(dict(digest=self.remote)), self.local]):
            self.manifest = self.operations.prepare(self.snapshot['run_id'], self.repository, self.environment, 'registry.example/test/app@' + self.remote)

    def approve_fixture(self):
        with self.store.transaction() as db:
            snapshot = self.store.load(db, self.snapshot['run_id'])
            target = self.manifest['target']
            snapshot.update(state='deploying')
            snapshot['approvals'].append(dict(id=uid(), state='approved', target=target, target_digest=digest(target)))
            self.store.save(db, snapshot, 'warning', 'synthetic release decision only')

    def test_recorded_release_repository_cannot_embed_credentials(self):
        bundle = export_recording(self.store.path, self.snapshot['run_id'])
        view = self.store.release_view(self.snapshot['run_id'])
        view['details']['repository']['url'] = 'https://synthetic:private@example.org/app.git'
        metadata = dict(id=uid(), kind='deployment', title='synthetic release', public_summary='synthetic', content_digest=digest(view))
        bundle['snapshot']['artifacts'].append(metadata)
        bundle['artifacts'].append(dict(metadata=metadata, content=view))
        bundle['manifest_digest'] = digest({k:v for k,v in bundle.items() if k != 'manifest_digest'})
        with self.assertRaises(DomainError):
            check(bundle)

    def test_missing_or_changed_approval_blocks_every_mutation(self):
        with patch.object(self.operations.git, 'push') as push, patch.object(self.operations.environment, 'deploy') as deploy:
            with self.assertRaises(DomainError):
                self.operations.apply(self.snapshot['run_id'], self.manifest, 'push')
            self.approve_fixture()
            changed = copy.deepcopy(self.manifest)
            changed['environment']['port'] += 1
            with self.assertRaises(DomainError):
                self.operations.apply(self.snapshot['run_id'], changed, 'deploy')
            push.assert_not_called()
            deploy.assert_not_called()

    def test_push_ack_loss_is_observed_once_not_repeated(self):
        self.approve_fixture()
        with patch.object(self.operations.git, 'head', side_effect=[None, 'a' * 40, 'a' * 40]), \
             patch.object(self.operations.git, 'push', side_effect=ModelUnavailable()) as push:
            self.assertEqual(self.operations.apply(self.snapshot['run_id'], self.manifest, 'push'), 'applied')
            self.assertEqual(self.operations.apply(self.snapshot['run_id'], self.manifest, 'push'), 'applied')
            push.assert_called_once()
        view = self.store.release_view(self.snapshot['run_id'])
        validate('ReleaseView', view)
        self.assertFalse(view['enabled'])
        self.assertEqual(view['target'], self.manifest['target'])
        self.assertEqual(view['operations'][0]['state'], 'applied')
        self.assertIsNotNone(view['operations'][0]['accepted_at'])
        self.assertIsNotNone(view['operations'][0]['observed_at'])
        self.assertIsNone(view['operations'][0]['volume_preserved'])
        self.assertNotIn(self.temp, canonical(view))
        live = self.store.snapshot(self.snapshot['run_id'])
        artifact = next(a for a in reversed(live['artifacts']) if a['kind'] == 'deployment')
        self.assertEqual(self.store.read_artifact(artifact['id']), view)
        event = self.store.events(live['run_id'], 0)[-1]
        self.assertEqual(event['operation_id'], view['operations'][0]['operation_id'])
        self.assertEqual(event['artifact_ids'], [artifact['id']])
        replay = self.store.create_run(live['project_id'], dict(mode='replay', source_run_id=live['run_id']))
        self.assertEqual(self.store.release_view(replay['run_id']), dict(view, run_id=replay['run_id']))

    def test_unknown_external_result_is_not_automatically_retried(self):
        self.approve_fixture()
        with patch.object(self.operations.git, 'head', side_effect=[None, ModelUnavailable(), None]), \
             patch.object(self.operations.git, 'push', side_effect=ModelUnavailable()) as push:
            self.assertEqual(self.operations.apply(self.snapshot['run_id'], self.manifest, 'push'), 'uncertain')
            self.assertEqual(self.operations.apply(self.snapshot['run_id'], self.manifest, 'push'), 'uncertain')
            push.assert_called_once()
        with self.store.transaction() as db:
            self.assertEqual(db.execute('SELECT state FROM operations').fetchone()[0], 'uncertain')
        with self.store.transaction() as db:
            snapshot = self.store.load(db, self.snapshot['run_id'])
            snapshot['state'] = 'paused'
            self.store.save(db, snapshot, 'warning', 'synthetic pause during result loss')
        with patch.object(self.operations.git, 'head', return_value='a' * 40), patch.object(self.operations.git, 'push') as push:
            self.assertEqual(self.operations.reconcile(self.snapshot['run_id'], self.manifest, 'push'), 'applied')
            push.assert_not_called()
        self.assertEqual(self.store.snapshot(self.snapshot['run_id'])['state'], 'paused')

    def test_local_deploy_and_rollback_keep_separate_idempotent_operations(self):
        self.approve_fixture()
        with patch.object(self.operations.environment, 'observe', side_effect=['not_applied', 'applied']), \
             patch.object(self.operations.environment, 'deploy') as deploy:
            self.assertEqual(self.operations.apply(self.snapshot['run_id'], self.manifest, 'deploy'), 'applied')
            deploy.assert_called_once_with(self.manifest, ANY)
        with patch.object(self.operations.environment, 'observe', side_effect=['applied', 'not_applied', 'not_applied']), \
             patch.object(self.operations.environment, 'rollback') as rollback:
            self.assertEqual(self.operations.apply(self.snapshot['run_id'], self.manifest, 'rollback'), 'applied')
            self.assertEqual(self.operations.apply(self.snapshot['run_id'], self.manifest, 'rollback'), 'applied')
            rollback.assert_called_once_with(self.manifest)
        environment = self.operations.environment
        with patch.object(self.operations.engine, 'runtime', return_value=self.local), patch.object(self.operations.engine, 'docker', return_value=''), patch.object(environment.pipeline, 'preview_services') as services:
            environment.deploy(self.manifest, lambda: True)
            candidate, operation, current = services.call_args.args
            self.assertEqual(candidate['image_digest'], self.local)
            self.assertEqual(operation['port'], 49101)
            self.assertNotEqual(operation['app'], operation['proxy'])
            self.assertEqual(operation['data_volume'], self.manifest['resources']['volume'])
            self.assertTrue(current())
        with patch.object(self.operations.engine, 'runtime', return_value=self.local), patch.object(self.operations.engine, 'docker', side_effect=[self.manifest['resources']['network'], '[{"Internal": false}]']), patch.object(environment.pipeline, 'preview_services') as services:
            with self.assertRaises(DomainError):
                environment.deploy(self.manifest, lambda: True)
            services.assert_not_called()

    def test_product_repository_and_missing_free_proof_are_blocked_before_network(self):
        with patch.object(self.operations.engine, 'docker') as docker:
            repository = dict(self.repository, url='https://github.com/tjgurdls9/skala-AIMiniProject.git')
            with self.assertRaises(DomainError):
                self.operations.prepare(self.snapshot['run_id'], repository, self.environment, 'registry.example/app@' + self.remote)
            with self.assertRaises(DomainError):
                self.operations.prepare(self.snapshot['run_id'], self.repository, dict(self.environment, free_verified=False), 'registry.example/app@' + self.remote)
            with self.assertRaises(DomainError):
                self.operations.prepare(self.snapshot['run_id'], dict(self.repository, auto_deploy=True), self.environment, 'registry.example/app@' + self.remote)
            docker.assert_not_called()

    def test_environment_observation_checks_isolation_proxy_and_health(self):
        resources = self.manifest['resources']
        host = dict(ReadonlyRootfs=True, Privileged=False, CapDrop=['ALL'], PortBindings={})
        actual = dict(Image=self.local, Config=dict(User='65534:65534'), HostConfig=host,
                      NetworkSettings=dict(Networks={resources['network']: {}}), State=dict(Running=True),
                      Mounts=[dict(Type='volume', Name=resources['volume'], Destination='/data'), dict(Type='tmpfs', Destination='/tmp')])
        proxy = dict(Image=self.local, Config=dict(User='65534:65534', Cmd=['python', '/checks/preview.py', resources['container'] + ':8080']),
                     HostConfig=dict(host, PortBindings={'8081/tcp': [dict(HostIp='127.0.0.1', HostPort='49101')]}),
                     NetworkSettings=dict(Networks={resources['network']: {}, resources['network'] + '-ingress': {}}), State=dict(Running=True),
                     Mounts=[dict(Type='bind', Source=str(ROOT / 'infra/checks'), Destination='/checks', RW=False)])
        def inspect(*args):
            if args[0] == 'ps':
                return resources['container'] + '\n' + resources['proxy']
            if args[0] == 'network':
                return '[{"Internal": true}]'
            return json.dumps([actual if args[1] == resources['container'] else proxy])
        with patch.object(self.operations.engine, 'docker', side_effect=inspect), patch('runner.release.httpx.Client') as client:
            client.return_value.__enter__.return_value.get.return_value.status_code = 200
            client.return_value.__enter__.return_value.get.return_value.json.return_value = dict(status='ok')
            self.assertEqual(self.operations.environment.observe(self.manifest), 'applied')
            actual['Mounts'].append(dict(Type='bind', Source='/private', Destination='/tmp'))
            with self.assertRaises(DomainError):
                self.operations.environment.observe(self.manifest)
