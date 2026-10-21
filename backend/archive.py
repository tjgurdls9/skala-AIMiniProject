"""Public-record transfer only. Imported records never create executable jobs or grants."""
import argparse
import copy
from contextlib import closing
import hashlib
import json
import platform
from pathlib import Path
import re
import subprocess
import sqlite3
from urllib.parse import urlsplit

from backend.contracts import ROOT, SECRET, canonical, digest, require, validate
from backend.store import Store, artifact_content, uid

MAX_BYTES = 16 * 1024 * 1024


def contract_digests():
    return {name: 'sha256:' + hashlib.sha256((ROOT / 'docs/planning' / name).read_bytes()).hexdigest()
            for name in ('protocol.v1.schema.json', 'http.v1.schema.json')}


def check(bundle):
    validate('RecordingBundle', bundle)
    payload = {k: v for k, v in bundle.items() if k != 'manifest_digest'}
    require(digest(payload) == bundle['manifest_digest'], 'INVALID_COMMAND', '기록 manifest 해시가 일치하지 않습니다.', 422)
    require(bundle['exporter']['contract_digests'] == contract_digests(), 'VERSION_CONFLICT', '기록과 현재 열람기의 계약 버전이 다릅니다.')
    raw = canonical(bundle)
    require(len(raw.encode()) <= MAX_BYTES, 'BODY_TOO_LARGE', '기록 크기 한도를 초과했습니다.', 413)
    require(not SECRET.search(raw) and not re.search(r'/(?:Users|home|private|tmp)/', raw), 'FORBIDDEN', '비밀 형식 또는 개인 호스트 경로가 포함된 기록은 이동하지 않습니다.', 403)
    snapshot, events = bundle['snapshot'], bundle['events']
    require(snapshot['project_id'] == bundle['project']['project_id'] and len(events) == snapshot['last_event_seq'] and
            [e['seq'] for e in events] == list(range(1, len(events) + 1)) and
            all(e['run_id'] == snapshot['run_id'] and e['mode'] == snapshot['mode'] for e in events) and
            events[-1]['occurred_at'] == bundle['recorded_at'] and events[-1]['state_version'] == snapshot['state_version'],
            'INVALID_COMMAND', '기록의 사건 순서/대상이 일치하지 않습니다.', 422)
    entries = {entry['metadata']['id']: entry for entry in bundle['artifacts']}
    require(len(entries) == len(bundle['artifacts']) and len(snapshot['artifacts']) == len(entries) and
            {a['id'] for a in snapshot['artifacts']} == set(entries), 'INVALID_COMMAND', '공개 아티팩트 목록이 일치하지 않습니다.', 422)
    for metadata in snapshot['artifacts']:
        entry = entries[metadata['id']]
        require(entry['metadata'] == metadata and digest(entry['content']) == metadata['content_digest'], 'INVALID_COMMAND', '아티팩트 해시/metadata가 일치하지 않습니다.', 422)
        if metadata['kind'] == 'spec':
            validate('PlanView', entry['content'])
            support = entry['content'].get('support')
            require(support is None or support['spec_version_id'] == entry['content']['spec_version_id'],
                    'INVALID_COMMAND', '지원 공백이 다른 명세에 연결됐습니다.', 422)
        elif metadata['kind'] in ('preview', 'retrieval', 'context', 'deployment'):
            name = {'preview': 'Preview', 'retrieval': 'RetrievalEvidence', 'context': 'ContextEvidence', 'deployment': 'ReleaseView'}[metadata['kind']]
            validate(name, entry['content'])
            if name == 'ContextEvidence':
                require(entry['content']['completed_fragments'] <= entry['content']['total_fragments'],
                        'INVALID_COMMAND', '완료 문맥 조각 수가 전체를 넘습니다.', 422)
            urls = ([entry['content']['url'], entry['content']['origin']] if name == 'Preview' else
                    [s['url'] for s in entry['content']['sources']] if name == 'RetrievalEvidence' else [])
            for url in urls:
                parsed = urlsplit(url)
                require(parsed.scheme in ('http', 'https', 'project') and parsed.hostname is not None and parsed.username is None and parsed.password is None,
                        'FORBIDDEN', '기록에 실행 가능한/비밀 포함 URL을 넣을 수 없습니다.', 403)
        if metadata['kind'] in ('spec', 'deployment'):
            repository = (entry['content']['repository'] if metadata['kind'] == 'spec' else
                          (entry['content']['details'] or {}).get('repository'))
            if repository:
                parsed = urlsplit(repository['url'])
                require(parsed.scheme == 'https' and parsed.hostname is not None and parsed.username is None and parsed.password is None,
                        'FORBIDDEN', '기록의 저장소 URL 형식을 확인하세요.', 403)
    specs = {e['content']['spec_version_id']: e['content'] for e in entries.values() if e['metadata']['kind'] == 'spec'}
    require(snapshot['spec_version_id'] is None or snapshot['spec_version_id'] in specs, 'INVALID_COMMAND', '현재 명세 원본이 없습니다.', 422)
    for report in snapshot['reports']:
        require(report['artifact_id'] in entries, 'INVALID_COMMAND', '검토 원본이 없습니다.', 422)
        content = entries[report['artifact_id']]['content']
        require(isinstance(content, dict) and digest(content) == report['content_digest'] and
                all(content.get(key) == report[key] for key in ('spec_version_id', 'commit_sha', 'image_digest', 'role', 'verdict')),
                'INVALID_COMMAND', '검토 원본과 명세/후보 결속이 일치하지 않습니다.', 422)
    for key in ('phases', 'sprints', 'tasks', 'approvals', 'reports'):
        require(len({entry['id'] for entry in snapshot[key]}) == len(snapshot[key]), 'INVALID_COMMAND', '기록 ID가 중복됩니다.', 422)
    task_ids = {t['id'] for t in snapshot['tasks']}
    phases = {p['id'] for p in snapshot['phases']}
    sprints = {s['id']: s for s in snapshot['sprints']}
    require(all(set(t['depends_on']).issubset(task_ids) and set(t['artifact_ids']).issubset(entries) for t in snapshot['tasks']),
            'INVALID_COMMAND', '작업 의존성/아티팩트 연결이 잘못됐습니다.', 422)
    require(all(s['phase_id'] in phases for s in sprints.values()) and
            all(t['phase_id'] in phases and t['sprint_id'] in sprints and sprints[t['sprint_id']]['phase_id'] == t['phase_id'] and t['spec_version_id'] in specs for t in snapshot['tasks']),
            'INVALID_COMMAND', '작업 계층/명세 연결이 잘못됐습니다.', 422)
    return entries, specs


def export_recording(database, run_id):
    with closing(sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN')
        snapshot = Store.load(db, run_id)
        project = dict(db.execute('SELECT id,title,created_at FROM projects WHERE id=?', (snapshot['project_id'],)).fetchone())
        project['project_id'] = project.pop('id')
        events = [json.loads(r[0]) for r in db.execute('SELECT body FROM events WHERE run_id=? ORDER BY seq', (run_id,))]
        artifacts = []
        for metadata in snapshot['artifacts']:
            row = db.execute('SELECT content,metadata FROM artifacts WHERE id=? AND public=1', (metadata['id'],)).fetchone()
            content = artifact_content(row)
            require(json.loads(row['metadata']) == metadata, 'TEMPORARILY_UNAVAILABLE', '공개 아티팩트 연결이 손상됐습니다.', 503)
            artifacts.append(dict(metadata=metadata, content=content))
    revision, dirty = None, True
    if (ROOT / '.git').exists():
        head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True, check=False)
        status = subprocess.run(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT, capture_output=True, text=True, check=False)
        revision = head.stdout.strip() if head.returncode == 0 else None
        dirty = bool(status.stdout) or status.returncode != 0
    bundle = dict(format='lifecycle-recording', version=1, recorded_at=events[-1]['occurred_at'], project=project,
                  snapshot=snapshot, events=events, artifacts=artifacts,
                  exporter=dict(revision=revision, dirty=dirty, python=platform.python_version(), contract_digests=contract_digests()))
    bundle['manifest_digest'] = digest(bundle)
    check(bundle)
    return bundle


def import_recording(store, bundle):
    entries, specs = check(bundle)
    with store.transaction() as db:
        previous = db.execute('SELECT run_id FROM recording_imports WHERE digest=?', (bundle['manifest_digest'],)).fetchone()
        if previous:
            snapshot = store.load(db, previous[0])
        else:
            snapshot = copy.deepcopy(bundle['snapshot'])
            project_id, run_id = uid(), uid()
            snapshot.update(project_id=project_id, run_id=run_id, mode='replay', replay_source=dict(
                source_run_id=bundle['snapshot']['run_id'], recorded_at=bundle['recorded_at'],
                manifest_digest=bundle['manifest_digest'], provenance='imported_unsigned'))
            validate('Snapshot', snapshot)
            db.execute('INSERT INTO projects VALUES (?, ?, ?)', (project_id, bundle['project']['title'], bundle['project']['created_at']))
            db.execute('INSERT INTO runs VALUES (?, ?, ?, NULL, NULL)', (run_id, project_id, canonical(snapshot)))
            for event in bundle['events']:
                event = dict(event, run_id=run_id, mode='replay')
                db.execute('INSERT INTO events VALUES (?, ?, ?)', (run_id, event['seq'], canonical(event)))
            for artifact_id, entry in entries.items():
                row = db.execute('SELECT metadata,content,public FROM artifacts WHERE id=?', (artifact_id,)).fetchone()
                if row:
                    require(row['public'] == 1 and json.loads(row['metadata']) == entry['metadata'] and json.loads(row['content']) == entry['content'],
                            'VERSION_CONFLICT', '기존 아티팩트를 덮어쓰지 않습니다.')
                else:
                    db.execute('INSERT INTO artifacts VALUES (?, ?, ?, ?, 1)', (artifact_id, run_id, canonical(entry['metadata']), canonical(entry['content'])))
            for spec_id, package in specs.items():
                row = db.execute('SELECT package FROM specs WHERE id=?', (spec_id,)).fetchone()
                require(row is None or json.loads(row[0]) == package, 'VERSION_CONFLICT', '기존 명세를 덮어쓰지 않습니다.')
                if row is None:
                    db.execute('INSERT INTO specs VALUES (?, ?, ?, ?)', (spec_id, run_id, canonical(package), bundle['recorded_at']))
            db.execute('INSERT INTO recording_imports VALUES (?, ?)', (bundle['manifest_digest'], run_id))
        result = dict(project_id=snapshot['project_id'], run_id=snapshot['run_id'], manifest_digest=bundle['manifest_digest'], read_only=True, provenance='imported_unsigned')
        validate('RecordingImportResult', result)
        return result


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'INVALID_COMMAND', '기록 JSON 키가 중복됐습니다.', 422)
        result[key] = value
    return result


def load_recording(path):
    with path.open('rb') as source:
        data = source.read(MAX_BYTES + 1)
    require(len(data) <= MAX_BYTES, 'BODY_TOO_LARGE', '기록 크기 한도를 초과했습니다.', 413)
    return json.loads(data, object_pairs_hook=unique_object, parse_constant=lambda _: require(False, 'INVALID_COMMAND', '유한 JSON 값이 필요합니다.', 422))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['export', 'import'])
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--file', type=Path, required=True)
    parser.add_argument('--run-id')
    args = parser.parse_args()
    if args.action == 'export':
        require(args.run_id, 'INVALID_COMMAND', 'run-id가 필요합니다.', 422)
        bundle = export_recording(args.database, args.run_id)
        with args.file.open('x') as target:
            target.write(canonical(bundle))
        print(bundle['manifest_digest'])
    else:
        print(canonical(import_recording(Store(args.database), load_recording(args.file))))
