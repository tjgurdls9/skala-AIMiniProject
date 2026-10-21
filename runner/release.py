"""Fixed Git/Docker adapters. No configured target or exact approval means no mutation."""
import json
from pathlib import Path
import re
import subprocess
import os
import httpx

from backend.contracts import ROOT, SECRET, canonical, digest, plan_inputs, require, validate
from backend.store import artifact_content, now
from runner.model import ModelUnavailable
from runner.pipeline import Pipeline


class GitRepository:
    @staticmethod
    def run(*args, cwd=None):
        try:
            result = subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', *args], cwd=cwd,
                                    stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120,
                                    env={**{k: os.environ[k] for k in ('PATH', 'HOME') if k in os.environ}, 'GIT_TERMINAL_PROMPT': '0', 'GIT_CONFIG_NOSYSTEM': '1'})
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ModelUnavailable('Git result unavailable') from error
        if result.returncode:
            raise ModelUnavailable('Git operation failed')
        require(len(result.stdout) <= 1024 * 1024 and not SECRET.search(result.stdout), 'TEMPORARILY_UNAVAILABLE', 'Git 결과 형식/한도를 확인하세요.', 503)
        return result.stdout

    def head(self, url, branch):
        lines = self.run('ls-remote', '--refs', url, 'refs/heads/' + branch).splitlines()
        require(len(lines) <= 1, 'INVALID_STATE', '원격 branch 결과가 모호합니다.')
        require(not lines or re.fullmatch(r'[a-f0-9]{40}(?:[a-f0-9]{24})?\trefs/heads/' + re.escape(branch), lines[0]),
                'INVALID_STATE', '원격 branch 형식이 잘못됐습니다.')
        return lines[0].split()[0] if lines else None

    def push(self, path, url, branch, commit):
        require(self.run('rev-parse', 'HEAD', cwd=path).strip() == commit and not self.run('status', '--porcelain', cwd=path).strip(),
                'VERSION_CONFLICT', '고정 후보 저장소가 변경됐습니다.')
        return self.run('push', '--porcelain', '--no-verify', '--', url, commit + ':refs/heads/' + branch, cwd=path)


class DockerEnvironment:
    def __init__(self, store):
        self.pipeline = Pipeline(store)
        self.engine = self.pipeline.engine

    @staticmethod
    def operation(manifest):
        return dict(network=manifest['resources']['network'], app=manifest['resources']['container'],
                    proxy=manifest['resources']['proxy'], data_volume=manifest['resources']['volume'], port=manifest['environment']['port'])

    def observe(self, manifest):
        name = manifest['resources']['container']
        names = self.engine.docker('ps', '-a', '--format', '{{.Names}}').splitlines()
        proxy_name = manifest['resources']['proxy']
        if name not in names or proxy_name not in names:
            return 'not_applied' if name not in names and proxy_name not in names else 'uncertain'
        actual = json.loads(self.engine.docker('inspect', name))[0]
        proxy = json.loads(self.engine.docker('inspect', proxy_name))[0]
        network = json.loads(self.engine.docker('network', 'inspect', manifest['resources']['network']))[0]
        volumes = [m for m in actual['Mounts'] if m['Destination'] != '/tmp']
        proxy_mounts = [m for m in proxy['Mounts'] if m['Destination'] != '/tmp']
        require(actual['Image'] == manifest['local_image_digest'] and
                actual['Config']['User'] == '65534:65534' and actual['HostConfig']['ReadonlyRootfs'] and
                not actual['HostConfig']['Privileged'] and 'ALL' in actual['HostConfig']['CapDrop'] and
                network['Internal'] is True and set(actual['NetworkSettings']['Networks']) == {manifest['resources']['network']} and
                not actual['HostConfig']['PortBindings'] and len(volumes) == 1 and
                all(m['Type'] == 'tmpfs' for m in actual['Mounts'] if m['Destination'] == '/tmp') and
                volumes[0]['Type'] == 'volume' and volumes[0]['Name'] == manifest['resources']['volume'] and volumes[0]['Destination'] == '/data' and
                proxy['Image'] == manifest['proxy_image_digest'] and proxy['Config']['User'] == '65534:65534' and
                proxy['HostConfig']['ReadonlyRootfs'] and not proxy['HostConfig']['Privileged'] and 'ALL' in proxy['HostConfig']['CapDrop'] and
                proxy['Config']['Cmd'] == ['python', '/checks/preview.py', name + ':8080'] and
                len(proxy_mounts) == 1 and proxy_mounts[0]['Type'] == 'bind' and proxy_mounts[0]['Source'] == str(ROOT / 'infra/checks') and
                proxy_mounts[0]['Destination'] == '/checks' and proxy_mounts[0]['RW'] is False and
                all(m['Type'] == 'tmpfs' for m in proxy['Mounts'] if m['Destination'] == '/tmp') and
                set(proxy['NetworkSettings']['Networks']) == {manifest['resources']['network'], manifest['resources']['network'] + '-ingress'} and
                proxy['HostConfig']['PortBindings']['8081/tcp'] == [{'HostIp': '127.0.0.1', 'HostPort': str(manifest['environment']['port'])}],
                'VERSION_CONFLICT', '환경의 이미지/승인 결속이 다릅니다.')
        if not actual['State']['Running'] or not proxy['State']['Running']:
            return 'uncertain'
        try:
            with httpx.Client(trust_env=False, timeout=2, follow_redirects=False) as client:
                response = client.get(f"http://127.0.0.1:{manifest['environment']['port']}/health")
                return 'applied' if response.status_code == 200 and response.json() == {'status': 'ok'} else 'uncertain'
        except (httpx.HTTPError, ValueError):
            return 'uncertain'

    def deploy(self, manifest, current):
        require(self.engine.runtime() == manifest['proxy_image_digest'], 'VERSION_CONFLICT', '승인한 보호 프록시 이미지가 변경됐습니다.')
        networks = self.engine.docker('network', 'ls', '--format', '{{.Name}}').splitlines()
        if manifest['resources']['network'] in networks:
            network = json.loads(self.engine.docker('network', 'inspect', manifest['resources']['network']))[0]
            require(network['Internal'] is True, 'FORBIDDEN', '생성 앱의 내부망 격리가 필요합니다.', 403)
        return self.pipeline.preview_services(dict(image_digest=manifest['local_image_digest'], template_id=manifest.get('template_id', 'requests-v1')), self.operation(manifest), current)

    def rollback(self, manifest):
        # The approved first-release rollback unpublishes this container and preserves its volume.
        state = self.observe(manifest)
        if state == 'not_applied':
            return
        require(self.pipeline.cleanup_preview(self.operation(manifest)), 'TEMPORARILY_UNAVAILABLE', '복구 정리 결과를 확인할 수 없습니다.', 503)


class ReleaseOperations:
    def __init__(self, store, current=lambda db: False):
        self.store, self.current = store, current
        self.git, self.environment = GitRepository(), DockerEnvironment(store)
        self.engine = self.environment.engine
        with store.transaction() as db:
            db.execute('CREATE TABLE IF NOT EXISTS release_manifests (digest TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id), body TEXT NOT NULL)')
            for action in ('UPDATE', 'DELETE'):
                db.execute(f"CREATE TRIGGER IF NOT EXISTS release_manifests_{action.lower()}_blocked BEFORE {action} ON release_manifests BEGIN SELECT RAISE(ABORT, 'immutable release manifest'); END")

    def prepare(self, run_id, repository, environment, image_reference):
        require(set(repository) == {'url', 'branch', 'auto_deploy'} and repository['auto_deploy'] is False, 'INVALID_COMMAND', '현재 어댑터는 자동 배포가 없는 확인된 branch만 지원합니다.', 422)
        require(re.fullmatch(r'https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?', repository['url']) and
                'tjgurdls9/skala-aiminiproject' not in repository['url'].casefold() and
                re.fullmatch(r'generated/[a-zA-Z0-9_-]+', repository['branch']), 'FORBIDDEN', '생성 앱 전용 원격 저장소/branch가 필요합니다.', 403)
        require(set(environment) == {'id', 'label', 'provider', 'exposure', 'port', 'free_verified', 'free_evidence'} and
                environment['provider'] == 'docker_local' and environment['exposure'] == 'local' and
                environment['free_verified'] is True and isinstance(environment['free_evidence'], str) and environment['free_evidence'] and
                isinstance(environment['port'], int) and not isinstance(environment['port'], bool) and 1024 <= environment['port'] <= 65535,
                'PROVIDER_NOT_FREE', '확인된 무료 로컬 Docker 환경/포트가 필요합니다.', 422)
        require(re.fullmatch(r'[a-z0-9][a-z0-9./:_-]+@sha256:[a-f0-9]{64}', image_reference), 'INVALID_COMMAND', '불변 registry manifest 참조가 필요합니다.', 422)
        require(not SECRET.search(canonical([repository, environment, image_reference])), 'FORBIDDEN', '출시 설정에 비밀 원문을 넣을 수 없습니다.', 403)
        with self.store.transaction() as db:
            snapshot = self.store.load(db, run_id)
            require(snapshot['mode'] == 'live' and snapshot['state'] == 'preview_ready', 'INVALID_STATE', '현재 프리뷰 후보가 필요합니다.')
            row = db.execute('SELECT package FROM specs WHERE id=?', (snapshot['spec_version_id'],)).fetchone()
            require(row is not None, 'INVALID_STATE', '기획 원본이 필요합니다.')
            package = json.loads(row[0])
            require(package.get('support', {}).get('implementation_allowed', True), 'INVALID_STATE', '기획 지원 공백이 남아 출시를 준비할 수 없습니다.')
            require(package['contract_digests'] == plan_inputs(self.store.template_id(db, run_id)) and package['repository'] == {k: repository[k] for k in ('url', 'branch')} and
                    package['deployment'] == {k: environment[k] for k in ('id', 'label', 'exposure')},
                    'STALE_APPROVAL', '저장소/환경을 포함한 새 기획 승인이 필요합니다.')
            require(any(a['state'] == 'approved' and a['target'] == dict(gate='plan', spec_version_id=snapshot['spec_version_id'], plan_digest=digest(package)) and a['target_digest'] == digest(a['target']) for a in snapshot['approvals']),
                    'STALE_APPROVAL', '현재 기획에 대한 사용자 승인이 필요합니다.')
            row = db.execute('SELECT body FROM candidates WHERE run_id=? AND spec_version_id=? ORDER BY rowid DESC LIMIT 1', (run_id, snapshot['spec_version_id'])).fetchone()
            require(row is not None, 'INVALID_STATE', '불변 후보가 필요합니다.')
            candidate = json.loads(row[0])
            reports = snapshot['reports']
            require(len(reports) == 2 and {r['role'] for r in reports} == {'validator', 'security'} and
                    all(r['verdict'] == 'pass' and r['spec_version_id'] == snapshot['spec_version_id'] and
                        r['commit_sha'] == candidate['commit_sha'] and r['image_digest'] == candidate['image_digest'] for r in reports),
                    'INVALID_STATE', '동일 후보의 두 독립 PASS 원본이 필요합니다.')
            for report in reports:
                row = db.execute('SELECT content,metadata FROM artifacts WHERE id=? AND public=1', (report['artifact_id'],)).fetchone()
                content = artifact_content(row)
                require(digest(content) == report['content_digest'] and all(content.get(k) == report[k] for k in ('role', 'spec_version_id', 'commit_sha', 'image_digest', 'verdict')),
                        'TEMPORARILY_UNAVAILABLE', '검토 원본을 확인할 수 없습니다.', 503)
        remote = json.loads(self.engine.docker('buildx', 'imagetools', 'inspect', image_reference, '--format', '{{json .Manifest}}'))
        registry_digest = image_reference.rsplit('@', 1)[1]
        require(remote['digest'] == registry_digest and self.engine.docker('image', 'inspect', image_reference, '--format', '{{.Id}}').strip() == candidate['image_digest'],
                'VERSION_CONFLICT', 'registry manifest와 검토한 로컬 이미지 결속을 확인하세요.')
        rollback = dict(action='unpublish_first_release', data_policy='preserve_volume_no_schema_migration', previous=None)
        configuration = dict(repository=repository, environment=environment, image_reference=image_reference,
                             local_image_digest=candidate['image_digest'], proxy_image_digest=self.engine.runtime(),
                             template_id=candidate.get('template_id', 'requests-v1'))
        target = dict(gate='release', spec_version_id=snapshot['spec_version_id'], plan_digest=digest(package), commit_sha=candidate['commit_sha'],
                      image_digest=registry_digest, environment_id=environment['id'], environment_config_digest=digest(configuration),
                      rollback_manifest_digest=digest(rollback), review_report_ids=sorted(r['id'] for r in reports))
        validate('ReleaseTarget', target)
        suffix = digest(target).split(':')[1][:32]
        manifest = dict(kind='deployment', target=target, **configuration, rollback=rollback, candidate_path=candidate['path'], resources=dict(
            container='lifecycle-' + suffix, proxy='lifecycle-' + suffix + '-1', network='lifecycle-' + suffix,
            volume=f"lifecycle-{run_id}-{snapshot['spec_version_id']}-data"))
        require(Path(candidate['path']).resolve().is_relative_to(self.engine.root), 'FORBIDDEN', '제품의 고정 후보만 출시할 수 있습니다.', 403)
        with self.store.transaction() as db:
            latest = self.store.load(db, run_id)
            require(latest == snapshot, 'VERSION_CONFLICT', '대상 준비 중 실행 상태가 변경됐습니다.')
            db.execute('INSERT OR IGNORE INTO release_manifests VALUES (?, ?, ?)', (digest(target), run_id, canonical(manifest)))
        return manifest

    def authorize(self, db, run_id, manifest):
        snapshot = self.store.load(db, run_id)
        target = manifest['target']
        row = db.execute('SELECT body FROM release_manifests WHERE digest=? AND run_id=?', (digest(target), run_id)).fetchone()
        package = db.execute('SELECT package FROM specs WHERE id=?', (snapshot['spec_version_id'],)).fetchone()
        require(row is not None and json.loads(row[0]) == manifest and self.current(db) and snapshot['mode'] == 'live' and
                snapshot['state'] == 'deploying' and snapshot['spec_version_id'] == target['spec_version_id'] and
                package is not None and digest(json.loads(package[0])) == target['plan_digest'] and json.loads(package[0])['contract_digests'] == plan_inputs(self.store.template_id(db, run_id)) and
                sorted(r['id'] for r in snapshot['reports']) == target['review_report_ids'] and
                len(snapshot['reports']) == 2 and {r['role'] for r in snapshot['reports']} == {'validator', 'security'} and
                all(r['verdict'] == 'pass' and r['spec_version_id'] == target['spec_version_id'] and r['commit_sha'] == target['commit_sha'] and r['image_digest'] == manifest['local_image_digest'] for r in snapshot['reports']) and
                any(a['state'] == 'approved' and a['target_digest'] == digest(target) and a['target'] == target for a in snapshot['approvals']),
                'STALE_APPROVAL', '현재 명세·후보·환경·원본 보고서·복구 계획에 대한 실제 사용자 승인이 필요합니다.')
        for report in snapshot['reports']:
            content = artifact_content(db.execute('SELECT content,metadata FROM artifacts WHERE id=? AND public=1', (report['artifact_id'],)).fetchone())
            require(digest(content) == report['content_digest'], 'TEMPORARILY_UNAVAILABLE', '출시 검토 원본이 손상됐습니다.', 503)
        return snapshot

    def record_state(self, db, run_id, manifest, action, state, observed_at=None):
        operation_id = digest([run_id, digest(manifest['target']), action])
        previous = db.execute('SELECT result FROM operations WHERE id=?', (operation_id,)).fetchone()
        old = json.loads(previous[0]) if previous else None
        reason = ('실행 의도를 기록했습니다. 실제 적용 완료가 아닙니다.' if state == 'pending' else
                  '정확한 외부 대상 조회로 적용을 확인했습니다. 볼륨 내용/DB 복원 검증은 별도입니다.' if state == 'applied' else
                  '외부 적용 여부를 확인할 수 없습니다. 응답 유실/불명 결과는 자동 재실행하지 않습니다.')
        evidence = dict(kind='deployment', action=action, accepted_at=old.get('accepted_at') if old else now(),
                        observed_at=observed_at if observed_at else old.get('observed_at') if old else None,
                        reason=reason, volume_preserved=None)
        db.execute('INSERT INTO operations VALUES (?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET state=excluded.state,result=excluded.result',
                   (operation_id, run_id, digest(manifest['target']), state, canonical(evidence)))
        snapshot = self.store.load(db, run_id)
        if not self.current(db) or snapshot['mode'] != 'live' or snapshot['spec_version_id'] != manifest['target']['spec_version_id']:
            return
        body = self.store.release_view(run_id, db)
        artifact = self.store.artifact(db, snapshot, 'deployment', '출시·복구 원장 근거', body)
        event = 'deployment_started' if state == 'pending' else 'operation_uncertain' if state == 'uncertain' else 'tool_finished' if action == 'push' else 'deployment_finished'
        self.store.save(db, snapshot, event, reason, bump=False, operation_id=operation_id, artifact_ids=[artifact['id']])

    def observed(self, manifest, action):
        try:
            return self.observe(manifest, action), now()
        except (ModelUnavailable, OSError, ValueError, KeyError, TypeError):
            return 'uncertain', None

    def reconcile(self, run_id, manifest, action):
        """Read a previously issued operation after execution authority expires."""
        require(action in ('push', 'deploy', 'rollback'), 'INVALID_COMMAND', '알려진 출시 동작이 필요합니다.', 422)
        operation_id = digest([run_id, digest(manifest['target']), action])
        with self.store.transaction() as db:
            saved = db.execute('SELECT body FROM release_manifests WHERE digest=? AND run_id=?', (digest(manifest['target']), run_id)).fetchone()
            operation = db.execute('SELECT id FROM operations WHERE id=? AND run_id=?', (operation_id, run_id)).fetchone()
            require(saved is not None and json.loads(saved[0]) == manifest and operation is not None, 'NOT_FOUND', '기존 출시 operation이 필요합니다.', 404)
        state, observed_at = self.observed(manifest, action)
        result = 'applied' if state == 'applied' else 'uncertain'
        with self.store.transaction() as db:
            self.record_state(db, run_id, manifest, action, result, observed_at)
        return result

    def observe(self, manifest, action):
        if action == 'push':
            head = self.git.head(manifest['repository']['url'], manifest['repository']['branch'])
            return 'applied' if head == manifest['target']['commit_sha'] else 'not_applied'
        state = self.environment.observe(manifest)
        return ('applied' if state == 'not_applied' else 'not_applied') if action == 'rollback' else state

    def apply(self, run_id, manifest, action):
        require(action in ('push', 'deploy', 'rollback'), 'INVALID_COMMAND', '알려진 출시 동작이 필요합니다.', 422)
        operation_id = digest([run_id, digest(manifest['target']), action])
        with self.store.transaction() as db:
            self.authorize(db, run_id, manifest)
            old = db.execute('SELECT state FROM operations WHERE id=?', (operation_id,)).fetchone()
        state, observed_at = self.observed(manifest, action)
        if old or state in ('applied', 'uncertain'):
            result = 'applied' if state == 'applied' else 'uncertain'
            with self.store.transaction() as db:
                self.authorize(db, run_id, manifest)
                self.record_state(db, run_id, manifest, action, result, observed_at)
            return result
        with self.store.transaction() as db:
            self.authorize(db, run_id, manifest)
            self.record_state(db, run_id, manifest, action, 'pending')
        try:
            with self.store.transaction() as db:
                self.authorize(db, run_id, manifest)
            if action == 'push':
                self.git.push(manifest['candidate_path'], manifest['repository']['url'], manifest['repository']['branch'], manifest['target']['commit_sha'])
            elif action == 'deploy':
                def current():
                    with self.store.transaction() as db:
                        self.authorize(db, run_id, manifest)
                    return True
                self.environment.deploy(manifest, current)
            else:
                self.environment.rollback(manifest)
        except (ModelUnavailable, OSError, ValueError, KeyError, TypeError):
            pass  # Acknowledgement loss is resolved only by observing the exact external target.
        state, observed_at = self.observed(manifest, action)
        result = 'applied' if state == 'applied' else 'uncertain'
        with self.store.transaction() as db:
            self.record_state(db, run_id, manifest, action, result, observed_at)
        return result
