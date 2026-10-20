"""Durable, source-bound planning steps; checkpoints contain no hidden reasoning."""
import copy
import json

from backend.contracts import SECRET, canonical, digest, plan_inputs, require, validate
from backend.store import now

BUDGET = 14000
FRAGMENT_BYTES = 2400


def fragments(requests):
    result = []
    for request in requests:
        start, size = 0, 0
        for offset, char in enumerate(request['content']):
            length = len(char.encode())
            if size + length > FRAGMENT_BYTES:
                text = request['content'][start:offset]
                result.append(dict(request_id=request['id'], offset=start, length=len(text), content_digest=digest(text), text=text))
                start, size = offset, 0
            size += length
        text = request['content'][start:]
        if text:
            result.append(dict(request_id=request['id'], offset=start, length=len(text), content_digest=digest(text), text=text))
    return result


def mandatory(packet):
    spec = packet.get('latest_spec')
    return dict(mandatory_policy=packet['mandatory_policy'],
                approved_spec={k: spec[k] for k in ('spec_version_id', 'goal', 'features', 'non_goals', 'acceptance', 'constraints')} if spec else None,
                unresolved_failures=packet['unresolved_failures'])


def bounded(packet):
    require(len(canonical(packet).encode()) <= BUDGET, 'INVALID_COMMAND',
            '필수 목표·제약·AC 또는 한 파일 자체가 문맥 예산을 초과했습니다. 원문을 보존했으니 작업 범위를 나누어 요청하세요.', 422)
    return packet


class PlanningContext:
    def __init__(self, store):
        self.store = store
        with store.transaction() as db:
            db.execute('CREATE TABLE IF NOT EXISTS context_steps (source_digest TEXT NOT NULL, step INTEGER NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(source_digest,step))')
            for action in ('UPDATE', 'DELETE'):
                db.execute(f"CREATE TRIGGER IF NOT EXISTS context_steps_{action.lower()}_blocked BEFORE {action} ON context_steps BEGIN SELECT RAISE(ABORT, 'immutable context'); END")

    async def plan(self, job, worker, schema):
        packet = job['packet']
        parts = fragments(packet['requests'])
        inputs = mandatory(packet)
        source = digest(dict(version=1, run_id=job['run_id'], requests=packet['requests'], policy=inputs['mandatory_policy'], approved=inputs['approved_spec'], inputs=plan_inputs()))
        job['context_evidence'] = dict(spec_version_id=packet['spec_version_id'], status='needs_input', source_digest=source,
                                      completed_fragments=0, total_fragments=len(parts),
                                      sources=[{k: v for k, v in p.items() if k != 'text'} for p in parts])
        previous = None
        for index, part in enumerate(parts):
            with self.store.transaction() as db:
                row = db.execute('SELECT body FROM context_steps WHERE source_digest=? AND step=?', (source, index)).fetchone()
            if row:
                previous = json.loads(row[0])
                validate('PlanDraft', previous)
                job['context_evidence']['completed_fragments'] = index + 1
                continue
            call = bounded(dict(role='planner', **mandatory(packet), original_or_correction=part,
                                accumulated_plan=previous, source_digest=source, fragment_index=index, total_fragments=len(parts),
                                template_contract=packet['template_contract'], instructions=packet['next_action'] +
                                ' Read this exact original/correction fragment in order. Merge it into accumulated_plan. Retain prior requirements and identify conflicts/unsupported requests in assumptions and changes. Never silently drop requirements. All fragments are reviewed before proposing approval.'))
            proposal = await worker.infer(job, call, schema)
            validate('PlanDraft', proposal)
            require(not SECRET.search(canonical(proposal)), 'INVALID_COMMAND', '모델 출력에 비밀 형식이 포함됐습니다.', 422)
            # Retain earlier requirements even when a later model forgets them; operator resolves conflicts.
            if previous:
                for key in ('features', 'non_goals', 'constraints', 'assumptions', 'changes'):
                    proposal[key] = list(dict.fromkeys(previous[key] + proposal[key]))
                criteria = {a['id']: a for a in previous['acceptance']}
                for item in proposal['acceptance']:
                    require(item['id'] not in criteria or item == criteria[item['id']], 'INVALID_COMMAND',
                            '문맥 조각 사이 AC 정의가 충돌합니다. 원문/정정을 확인하고 기획 범위를 나누세요.', 422)
                    criteria[item['id']] = item
                proposal['acceptance'] = list(criteria.values())
                if previous['goal'] != proposal['goal']:
                    proposal['changes'] = list(dict.fromkeys(proposal['changes'] + ['이전 조각 목표: ' + previous['goal']]))
                validate('PlanDraft', proposal)
            with self.store.transaction() as db:
                require(worker.attempt_active(db, job) and worker.owns(db), 'TEMPORARILY_UNAVAILABLE', '문맥 인계 시도가 만료됐습니다.', 503)
                current = self.store.load(db, job['run_id'])
                require(current['state_version'] == job['version'] and current['state'] == 'planning', 'INVALID_STATE', '문맥 준비 중 상태가 변경됐습니다.')
                db.execute('INSERT INTO context_steps VALUES (?, ?, ?, ?)', (source, index, canonical(proposal), now()))
            previous = copy.deepcopy(proposal)
            job['context_evidence']['completed_fragments'] = index + 1
        require(previous is not None, 'INVALID_COMMAND', '보존된 요청 원문이 필요합니다.', 422)
        job['context_evidence']['status'] = 'ready'
        validate('ContextEvidence', job['context_evidence'])
        return previous


async def implement(store, session, job, worker, files, evidence, writable, schema):
    """Read one file and exact request fragment per call; reconcile persisted patch intent."""
    parts = fragments(job['packet']['requests'])
    source = digest([1, job['run_id'], job['packet']['spec_version_id'], parts, writable, plan_inputs()])
    with store.transaction() as db:
        db.execute('CREATE TABLE IF NOT EXISTS build_steps (source TEXT NOT NULL, step INTEGER NOT NULL, path TEXT NOT NULL, expected TEXT NOT NULL, content TEXT NOT NULL, state TEXT NOT NULL, PRIMARY KEY(source,step))')
        db.execute("CREATE TRIGGER IF NOT EXISTS build_steps_content_immutable BEFORE UPDATE ON build_steps WHEN OLD.source!=NEW.source OR OLD.step!=NEW.step OR OLD.path!=NEW.path OR OLD.expected!=NEW.expected OR OLD.content!=NEW.content BEGIN SELECT RAISE(ABORT, 'immutable patch intent'); END")
    for file_index, original in enumerate(f for f in files if f['path'] in writable):
        current = dict(original)
        for part_index, part in enumerate(parts):
            step = file_index * len(parts) + part_index
            with store.transaction() as db:
                row = db.execute('SELECT * FROM build_steps WHERE source=? AND step=?', (source, step)).fetchone()
            if row and row['state'] == 'applied':
                continue
            if row is None:
                packet = bounded(dict(role='builder', **mandatory(job['packet']), file=current,
                    original_or_correction=part, source_digest=source, fragment_index=part_index, total_fragments=len(parts),
                    retrieved_documents=evidence[:1], template_contract=job['packet']['template_contract'],
                    next_action='Implement the approved spec using this exact original/correction fragment as supporting input. Return only this assigned file as a whole replacement when needed, or empty files when already correct. Preserve existing implementation/data/API and h-based Vue renderer. No new dependencies, external URLs, HTML injection, eval or approval.'))
                proposal = await worker.infer(job, packet, schema)
                from jsonschema import Draft202012Validator
                Draft202012Validator(schema).validate(proposal)
                require(not SECRET.search(canonical(proposal)) and len(proposal['files']) <= 1 and
                        all(f['path'] == current['path'] for f in proposal['files']), 'FORBIDDEN', '분해된 작업의 담당 파일만 수정할 수 있습니다.', 403)
                content = proposal['files'][0]['content'] if proposal['files'] else current['content']
                with store.transaction() as db:
                    require(worker.pipeline.valid(db, job, worker) is not None, 'TEMPORARILY_UNAVAILABLE', '패치 시도가 만료됐습니다.', 503)
                    db.execute('INSERT INTO build_steps VALUES (?, ?, ?, ?, ?, ?)',
                               (source, step, current['path'], current['content_digest'], content, 'pending'))
                row = dict(path=current['path'], expected=current['content_digest'], content=content)
            output_digest = digest(row['content'])
            require(current['content_digest'] in (row['expected'], output_digest), 'VERSION_CONFLICT', '저장된 패치와 작업 파일이 충돌합니다. 원본/후보를 확인하세요.')
            if current['content_digest'] != output_digest:
                result = await session.call_tool('patch_file', dict(path=row['path'], content=row['content'], expected_digest=row['expected']))
                require(not result.isError, 'VERSION_CONFLICT', '패치 권한 또는 파일 버전이 바뀌었습니다.')
            with store.transaction() as db:
                require(worker.pipeline.valid(db, job, worker) is not None, 'TEMPORARILY_UNAVAILABLE', '패치 확인 시도가 만료됐습니다.', 503)
                db.execute("UPDATE build_steps SET state='applied' WHERE source=? AND step=?", (source, step))
            current.update(content=row['content'], content_digest=output_digest)
