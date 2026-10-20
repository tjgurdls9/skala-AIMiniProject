// 합성 예시 공통 재료 — 실제 실행 기록이 아니다. 해시·커밋은 반복 패턴으로 만들어 실제 값처럼 보이지 않게 했다.
import type { Approval, Artifact, PlanView, ReviewReport, RunEvent, RunState, Snapshot, Task } from '../api/types'

export const RUN_ID = 'example-run'
export const PROJECT_ID = 'example-project'
export const SPEC_V1 = 'spec-v1'
export const SPEC_V2 = 'spec-v2'

export const fakeDigest = (pair: string): string => `sha256:${pair.repeat(32)}`
export const fakeCommit = (pair: string): string => pair.repeat(20)

export const PHASES: Snapshot['phases'] = [
  { id: 'ph-plan', title: '기획', order: 0 },
  { id: 'ph-build', title: '구현', order: 1 },
  { id: 'ph-review', title: '독립 검토', order: 2 },
  { id: 'ph-release', title: '프리뷰·출시', order: 3 },
]

export const SPRINTS: Snapshot['sprints'] = [
  { id: 'sp-1', phase_id: 'ph-plan', title: 'Sprint 1 · 기획 확정', goal: '요청을 목표·범위·AC로 정리하고 승인받는다', acceptance_ids: ['AC-1'] },
  { id: 'sp-2', phase_id: 'ph-build', title: 'Sprint 2 · 데이터·API', goal: '합성 문의 CSV 적재와 분류 API를 만든다', acceptance_ids: ['AC-2', 'AC-3'] },
  { id: 'sp-3', phase_id: 'ph-build', title: 'Sprint 3 · 화면·통합', goal: '문의 목록·상태 변경 화면을 API와 연결한다', acceptance_ids: ['AC-4'] },
  { id: 'sp-4', phase_id: 'ph-review', title: 'Sprint 4 · 검증·보안', goal: '같은 후보를 검증과 보안이 각자 검토한다', acceptance_ids: ['AC-2', 'AC-3', 'AC-4', 'AC-5'] },
  { id: 'sp-5', phase_id: 'ph-release', title: 'Sprint 5 · 프리뷰·출시', goal: '프리뷰 확인 후 승인된 환경에 배포한다', acceptance_ids: ['AC-5'] },
]

type TaskSeed = Omit<Task, 'state' | 'reason' | 'spec_version_id'>

const TASK_SEEDS: TaskSeed[] = [
  { id: 't-plan', phase_id: 'ph-plan', sprint_id: 'sp-1', role: 'planner', work_kind: 'planning', title: '요청 분석·기획안 작성', depends_on: [], acceptance_ids: ['AC-1'], artifact_ids: ['a-request', 'a-spec'] },
  { id: 't-contract', phase_id: 'ph-build', sprint_id: 'sp-2', role: 'builder', work_kind: 'contract', title: '문의 API 계약 정의', depends_on: ['t-plan'], acceptance_ids: ['AC-2'], artifact_ids: ['a-contract'] },
  { id: 't-data', phase_id: 'ph-build', sprint_id: 'sp-2', role: 'builder', work_kind: 'ai_data', title: '합성 문의 CSV 적재·분류 규칙', depends_on: ['t-contract'], acceptance_ids: ['AC-2'], artifact_ids: ['a-diff-data'] },
  { id: 't-api', phase_id: 'ph-build', sprint_id: 'sp-2', role: 'builder', work_kind: 'backend', title: '문의 조회·상태 변경 API', depends_on: ['t-contract'], acceptance_ids: ['AC-3'], artifact_ids: ['a-diff-api', 'a-test-api'] },
  { id: 't-infra', phase_id: 'ph-build', sprint_id: 'sp-2', role: 'builder', work_kind: 'infra', title: '컨테이너 이미지 빌드 구성', depends_on: ['t-api'], acceptance_ids: ['AC-5'], artifact_ids: [] },
  { id: 't-ui', phase_id: 'ph-build', sprint_id: 'sp-3', role: 'builder', work_kind: 'frontend', title: '문의 목록·상세 화면', depends_on: ['t-api'], acceptance_ids: ['AC-4'], artifact_ids: ['a-diff-ui'] },
  { id: 't-int', phase_id: 'ph-build', sprint_id: 'sp-3', role: 'builder', work_kind: 'integration', title: '화면·API 통합 확인', depends_on: ['t-ui', 't-data'], acceptance_ids: ['AC-4'], artifact_ids: ['a-build'] },
  { id: 't-validate', phase_id: 'ph-review', sprint_id: 'sp-4', role: 'validator', work_kind: 'validation', title: '후보 커밋 기능 검증', depends_on: ['t-int'], acceptance_ids: ['AC-2', 'AC-3', 'AC-4'], artifact_ids: ['a-validation'] },
  { id: 't-security', phase_id: 'ph-review', sprint_id: 'sp-4', role: 'security', work_kind: 'security', title: '후보 커밋 보안 점검', depends_on: ['t-int'], acceptance_ids: ['AC-5'], artifact_ids: ['a-security'] },
  { id: 't-release', phase_id: 'ph-release', sprint_id: 'sp-5', role: 'release', work_kind: 'release', title: '승인된 이미지 배포·상태 확인', depends_on: ['t-validate', 't-security'], acceptance_ids: ['AC-5'], artifact_ids: ['a-deploy'] },
]

export type TaskStateMap = Partial<Record<string, Task['state'] | { state: Task['state']; reason: string }>>

/** 지정하지 않은 작업은 pending */
export function buildTasks(states: TaskStateMap, extra: Task[] = [], spec = SPEC_V1): Task[] {
  const seeded = TASK_SEEDS.map((seed): Task => {
    const entry = states[seed.id] ?? 'pending'
    const base: Task = { ...seed, spec_version_id: spec, state: typeof entry === 'string' ? entry : entry.state }
    return typeof entry === 'string' ? base : { ...base, reason: entry.reason }
  })
  return [...seeded, ...extra]
}

const ARTIFACT_LIST: Artifact[] = [
  { id: 'a-request', title: '최초 요청 원문', kind: 'request', content_digest: fakeDigest('a1'), public_summary: '고객 문의를 분류하고 처리 상태를 관리하는 작은 대시보드가 필요하다.' },
  { id: 'a-spec', title: '기획안 v1', kind: 'spec', content_digest: fakeDigest('a2'), public_summary: '목표·기능 4개·비범위 3개·AC 5개·스택·무료 정책' },
  { id: 'a-contract', title: '문의 API 계약', kind: 'contract', content_digest: fakeDigest('a3'), public_summary: 'GET /inquiries, PATCH /inquiries/{id}/status' },
  { id: 'a-diff-data', title: '데이터 적재 변경', kind: 'code_diff', content_digest: fakeDigest('a4'), public_summary: 'seed/inquiries.csv 적재, 키워드 분류 규칙 6개' },
  { id: 'a-diff-api', title: 'API 변경', kind: 'code_diff', content_digest: fakeDigest('a5'), public_summary: 'FastAPI 라우터 2개, SQLite 모델 1개' },
  { id: 'a-test-api', title: 'API 테스트 결과', kind: 'test_result', content_digest: fakeDigest('a6'), public_summary: '12개 중 12개 통과 (합성 예시 수치)' },
  { id: 'a-diff-ui', title: '화면 변경', kind: 'code_diff', content_digest: fakeDigest('a7'), public_summary: 'Vue 목록·상세·상태 변경 컴포넌트' },
  { id: 'a-build', title: '후보 이미지 빌드', kind: 'build', content_digest: fakeDigest('a8'), public_summary: '후보 커밋 cdcd… → 이미지 digest b1b1…' },
  { id: 'a-validation', title: '검증 보고서', kind: 'test_result', content_digest: fakeDigest('a9'), public_summary: 'AC-2·3·4 확인. 상세는 검증 원본 보고서' },
  { id: 'a-security', title: '보안 보고서', kind: 'security_result', content_digest: fakeDigest('b0'), public_summary: '의존성·비밀·입력 검증 점검 결과 원본' },
  { id: 'a-preview', title: '프리뷰', kind: 'preview', content_digest: fakeDigest('b2'), public_summary: '격리 프리뷰 — 합성 예시에서는 주소가 없다' },
  { id: 'a-deploy', title: '배포 결과', kind: 'deployment', content_digest: fakeDigest('b3'), public_summary: '환경 env-staging, 상태 확인 3회 정상 (합성 예시)' },
]

export function artifacts(ids: string[]): Artifact[] {
  return ARTIFACT_LIST.filter((a) => ids.includes(a.id))
}

export const PLAN_VIEW: PlanView = {
  spec_version_id: SPEC_V1,
  goal: '합성 고객 문의 CSV를 분류하고 담당자가 처리 상태를 바꿀 수 있는 대시보드를 만든다.',
  features: ['문의 목록·검색', '키워드 기반 자동 분류', '처리 상태 변경과 이력', '분류별 건수 요약'],
  non_goals: ['실제 고객 개인정보 사용', '다중 사용자 권한 관리', '외부 메일 연동'],
  acceptance: [
    { id: 'AC-1', title: '기획 승인', description: '목표·범위·AC·대상이 승인된 버전으로 고정된다.' },
    { id: 'AC-2', title: '분류', description: '합성 CSV 200건이 6개 분류 중 하나로 저장된다.' },
    { id: 'AC-3', title: '상태 변경 API', description: '상태 변경이 이력과 함께 저장되고 잘못된 상태는 422로 거절된다.' },
    { id: 'AC-4', title: '화면', description: '목록·상세·상태 변경이 390px에서도 키보드로 가능하다.' },
    { id: 'AC-5', title: '검토·배포', description: '검증·보안이 같은 후보를 통과하고 승인된 이미지만 배포된다.' },
  ],
  constraints: ['FastAPI + Vue + SQLite 템플릿', '무료 로컬 모델만 사용'],
  assumptions: ['문의 데이터는 합성 CSV로 대체한다'],
  changes: ['최초 요청의 "메일 자동 회신"을 비범위로 옮김'],
  stack: ['FastAPI', 'Vue 3', 'SQLite', 'Docker Compose'],
  repository: null,
  deployment: null,
  free_policy: 'Local Ollama Qwen/DeepSeek only; no paid fallback or external API.',
  allowed_tools: ['문서 검색', '작업 파일 읽기·패치', '검증 도구 실행'],
  contract_digests: { 'protocol.v1': fakeDigest('c1'), 'http.v1': fakeDigest('c2') },
}

export const PLAN_APPROVAL_PENDING: Approval = {
  id: 'ap-plan-1',
  state: 'pending',
  target_digest: fakeDigest('d1'),
  target: { gate: 'plan', spec_version_id: SPEC_V1, plan_digest: fakeDigest('d0') },
}

export const PLAN_APPROVAL_DONE: Approval = {
  id: 'ap-plan-1',
  state: 'approved',
  target_digest: fakeDigest('d1'),
  target: { gate: 'plan', spec_version_id: SPEC_V1, plan_digest: fakeDigest('d0') },
  decided_by: 'operator',
  decided_at: '2026-10-20T09:12:00+09:00',
}

export const CANDIDATE = { commit: fakeCommit('cd'), image: fakeDigest('b1') }

export function report(role: ReviewReport['role'], verdict: ReviewReport['verdict'], id = `rp-${role}`): ReviewReport {
  return {
    id,
    role,
    spec_version_id: SPEC_V1,
    commit_sha: CANDIDATE.commit,
    image_digest: CANDIDATE.image,
    verdict,
    artifact_id: role === 'validator' ? 'a-validation' : 'a-security',
    content_digest: fakeDigest(role === 'validator' ? 'e1' : 'e2'),
  }
}

export interface SnapshotInput {
  state: RunState
  stateVersion: number
  lastSeq: number
  tasks: Task[]
  approvals?: Approval[]
  reports?: ReviewReport[]
  artifactIds: string[]
  reason?: string
}

export function buildSnapshot(input: SnapshotInput): Snapshot {
  const snapshot: Snapshot = {
    kind: 'snapshot',
    protocol_version: 1,
    project_id: PROJECT_ID,
    run_id: RUN_ID,
    mode: 'live', // 스키마상 필수. 화면의 LIVE 배지는 연결 출처로 정하므로 예시를 LIVE로 표시하지 않는다.
    state: input.state,
    state_version: input.stateVersion,
    last_event_seq: input.lastSeq,
    spec_version_id: SPEC_V1,
    phases: PHASES,
    sprints: SPRINTS,
    tasks: input.tasks,
    approvals: input.approvals ?? [],
    reports: input.reports ?? [],
    artifacts: artifacts(input.artifactIds),
  }
  return input.reason ? { ...snapshot, reason: input.reason } : snapshot
}

type EventSeed = [RunEvent['event_type'], string, Partial<Pick<RunEvent, 'task_id' | 'sprint_id' | 'phase_id' | 'artifact_ids' | 'reason' | 'command_id'>>?]

/** 사건 seq·상태 버전·시각을 순서대로 채운다. 시각은 합성 값이다. */
export function buildEvents(seeds: EventSeed[], startSeq = 1, startVersion = 1): RunEvent[] {
  const start = Date.parse('2026-10-20T09:00:00+09:00')
  return seeds.map(([type, summary, extra], i): RunEvent => ({
    kind: 'event',
    protocol_version: 1,
    event_id: `ev-${startSeq + i}`,
    seq: startSeq + i,
    run_id: RUN_ID,
    mode: 'live',
    state_version: startVersion + Math.floor(i / 2),
    occurred_at: new Date(start + (startSeq + i) * 47_000).toISOString(),
    event_type: type,
    summary,
    artifact_ids: extra?.artifact_ids ?? [],
    ...(extra?.task_id ? { task_id: extra.task_id } : {}),
    ...(extra?.sprint_id ? { sprint_id: extra.sprint_id } : {}),
    ...(extra?.reason ? { reason: extra.reason } : {}),
  }))
}
