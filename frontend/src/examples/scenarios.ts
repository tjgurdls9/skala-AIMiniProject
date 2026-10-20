// 합성 예시 시나리오 — 화면 상태를 보여주기 위한 것이며 실제 실행·기록 재생이 아니다.
import type { Environment, RunEvent, Snapshot } from '../api/types'
import {
  CANDIDATE, PLAN_APPROVAL_DONE, PLAN_APPROVAL_PENDING, PLAN_VIEW, SPEC_V1,
  buildEvents, buildSnapshot, buildTasks, fakeDigest, report, type SnapshotInput,
} from './base'

export interface ExampleScenario {
  id: string
  label: string
  description: string
  snapshot: Snapshot
  events: RunEvent[]
  /** 연결 후 일정 간격으로 흘려보내는 합성 사건(상태 버전을 올리지 않는 근거 사건만) */
  tail: RunEvent[]
  artifactBodies: Record<string, unknown>
  environments: Record<string, Environment>
}

type Seeds = Parameters<typeof buildEvents>[0]

const PLAN_EVENTS: Seeds = [
  ['run_state_changed', '실행 시작 · 기획 단계', {}],
  ['task_started', '요청 분석 시작', { task_id: 't-plan', sprint_id: 'sp-1' }],
  ['retrieval_finished', '기획 양식·템플릿 문서 3건 검색', { task_id: 't-plan', sprint_id: 'sp-1' }],
  ['context_saved', '최초 요청 원문과 정정 1건을 문맥 패킷에 저장', { task_id: 't-plan', sprint_id: 'sp-1' }],
  ['task_finished', '기획안 v1 작성 완료', { task_id: 't-plan', sprint_id: 'sp-1', artifact_ids: ['a-spec'] }],
  ['plan_proposed', '기획안 v1 제시', { artifact_ids: ['a-spec'] }],
  ['approval_requested', '기획 승인 요청 · 승인 전에는 구현을 시작하지 않음', {}],
  ['run_state_changed', '기획 승인 대기', {}],
]

const BUILD_EVENTS: Seeds = [
  ['approval_decided', '기획 v1 승인', {}],
  ['run_state_changed', '구현 단계 시작', {}],
  ['task_started', 'API 계약 정의 시작', { task_id: 't-contract', sprint_id: 'sp-2' }],
  ['task_finished', 'API 계약 정의 완료', { task_id: 't-contract', sprint_id: 'sp-2', artifact_ids: ['a-contract'] }],
  ['task_started', '데이터 적재 시작', { task_id: 't-data', sprint_id: 'sp-2' }],
  ['task_started', 'API 구현 시작', { task_id: 't-api', sprint_id: 'sp-2' }],
  ['tool_finished', '데이터 적재 테스트 통과', { task_id: 't-data', sprint_id: 'sp-2', artifact_ids: ['a-diff-data'] }],
  ['task_finished', '데이터 적재 완료', { task_id: 't-data', sprint_id: 'sp-2' }],
]

const REVIEW_EVENTS: Seeds = [
  ['tool_finished', 'API 테스트 12건 통과', { task_id: 't-api', sprint_id: 'sp-2', artifact_ids: ['a-test-api'] }],
  ['task_finished', 'API 구현 완료', { task_id: 't-api', sprint_id: 'sp-2' }],
  ['task_finished', '화면 구현 완료', { task_id: 't-ui', sprint_id: 'sp-3', artifact_ids: ['a-diff-ui'] }],
  ['task_finished', '통합·후보 이미지 빌드 완료', { task_id: 't-int', sprint_id: 'sp-3', artifact_ids: ['a-build'] }],
  ['run_state_changed', '독립 검토 시작 · 같은 후보 커밋', {}],
  ['task_started', '기능 검증 시작', { task_id: 't-validate', sprint_id: 'sp-4' }],
  ['task_started', '보안 점검 시작', { task_id: 't-security', sprint_id: 'sp-4' }],
]

function scenario(
  meta: Pick<ExampleScenario, 'id' | 'label' | 'description'>,
  seeds: Seeds,
  input: Omit<SnapshotInput, 'stateVersion' | 'lastSeq'>,
  tail: Seeds = [],
  environments: Record<string, Environment> = {},
): ExampleScenario {
  const events = buildEvents(seeds)
  const last = events.at(-1)
  const stateVersion = last?.state_version ?? 0
  const snapshot = buildSnapshot({ ...input, stateVersion, lastSeq: last?.seq ?? 0 })
  const tailEvents = buildEvents(tail, events.length + 1, stateVersion).map((e) => ({ ...e, state_version: stateVersion }))
  return { ...meta, snapshot, events, tail: tailEvents, artifactBodies: { 'a-spec': PLAN_VIEW }, environments }
}

const STAGING: Environment = { id: 'env-staging', label: '스테이징 (합성)', exposure: 'private' }

const RELEASE_TARGET = {
  gate: 'release' as const,
  spec_version_id: SPEC_V1,
  plan_digest: fakeDigest('d0'),
  commit_sha: CANDIDATE.commit,
  image_digest: CANDIDATE.image,
  environment_id: 'env-staging',
  environment_config_digest: fakeDigest('f1'),
  rollback_manifest_digest: fakeDigest('f2'),
  review_report_ids: ['rp-validator', 'rp-security'],
}

const DONE_BUILD = { 't-plan': 'succeeded', 't-contract': 'succeeded', 't-data': 'succeeded', 't-api': 'succeeded', 't-infra': 'succeeded', 't-ui': 'succeeded', 't-int': 'succeeded' } as const
const BUILD_ARTIFACTS = ['a-request', 'a-spec', 'a-contract', 'a-diff-data', 'a-diff-api', 'a-test-api', 'a-diff-ui', 'a-build']

export const SCENARIOS: ExampleScenario[] = [
  scenario(
    { id: 'plan-approval', label: '기획 승인 대기', description: '기획안 v1을 읽고 승인하거나 수정을 요청하는 단계' },
    PLAN_EVENTS,
    { state: 'awaiting_plan_approval', tasks: buildTasks({ 't-plan': 'succeeded' }), approvals: [PLAN_APPROVAL_PENDING], artifactIds: ['a-request', 'a-spec'] },
  ),
  scenario(
    { id: 'building', label: '구현 중', description: 'Sprint 2 진행 중. 선행 대기·차단 이유와 근거 사건이 흐른다' },
    [...PLAN_EVENTS, ...BUILD_EVENTS],
    {
      state: 'building',
      tasks: buildTasks({ 't-plan': 'succeeded', 't-contract': 'succeeded', 't-data': 'succeeded', 't-api': 'running', 't-infra': { state: 'blocked', reason: '컨테이너 실행기 미연결 — 자원 준비 필요' } }),
      approvals: [PLAN_APPROVAL_DONE],
      artifactIds: ['a-request', 'a-spec', 'a-contract', 'a-diff-data'],
    },
    [
      ['retrieval_finished', 'FastAPI 라우터 예시 문서 2건 검색', { task_id: 't-api', sprint_id: 'sp-2' }],
      ['tool_finished', '정적 검사 통과', { task_id: 't-api', sprint_id: 'sp-2' }],
      ['context_saved', 'API 작업 중간 인계 저장', { task_id: 't-api', sprint_id: 'sp-2' }],
      ['tool_finished', '단위 테스트 7/12 통과 — 진행 중', { task_id: 't-api', sprint_id: 'sp-2' }],
    ],
  ),
  scenario(
    { id: 'quota', label: '무료 한도 대기', description: '무료 공급자 한도 소진. 유료 전환 없이 대기한다' },
    [...PLAN_EVENTS, ...BUILD_EVENTS, ['quota_wait', '무료 추론 한도 소진 · 유료 전환 없음', { task_id: 't-api', reason: '로컬 추론 슬롯 1개 사용 중, 대기열 2건' }], ['run_state_changed', '무료 한도 대기', {}]],
    {
      state: 'waiting_quota',
      reason: '무료 추론 한도 소진. 유료 공급자로 자동 전환하지 않습니다.',
      tasks: buildTasks({ 't-plan': 'succeeded', 't-contract': 'succeeded', 't-data': 'succeeded', 't-api': { state: 'pending', reason: '무료 한도 대기' } }),
      approvals: [PLAN_APPROVAL_DONE],
      artifactIds: ['a-request', 'a-spec', 'a-contract', 'a-diff-data'],
    },
  ),
  scenario(
    { id: 'review-split', label: '검증 통과 · 보안 실패', description: '두 검토가 다른 판정을 냈다. 출시는 차단되고 수정 작업이 생긴다' },
    [...PLAN_EVENTS, ...BUILD_EVENTS, ...REVIEW_EVENTS,
      ['review_submitted', '검증 보고서 제출: 통과', { task_id: 't-validate', artifact_ids: ['a-validation'] }],
      ['review_submitted', '보안 보고서 제출: 실패 — 상태 변경 API 입력 검증 누락', { task_id: 't-security', artifact_ids: ['a-security'] }],
      ['warning', '보안 실패로 출시 차단 · 수정 작업 생성', { task_id: 't-fix' }],
    ],
    {
      state: 'building',
      tasks: buildTasks({ ...DONE_BUILD, 't-validate': 'succeeded', 't-security': { state: 'failed', reason: '입력 검증 누락 (보안 보고서 참조)' } }, [
        { id: 't-fix', phase_id: 'ph-build', sprint_id: 'sp-3', spec_version_id: SPEC_V1, role: 'builder', work_kind: 'backend', title: '상태 변경 입력 검증 보완', state: 'ready', depends_on: ['t-security'], acceptance_ids: ['AC-3', 'AC-5'], artifact_ids: [], reason: '보안 실패에서 생성된 수정 작업' },
      ]),
      approvals: [PLAN_APPROVAL_DONE],
      reports: [report('validator', 'pass'), report('security', 'fail')],
      artifactIds: [...BUILD_ARTIFACTS, 'a-validation', 'a-security'],
    },
  ),
  scenario(
    { id: 'preview', label: '프리뷰 확인', description: '두 검토 통과 후 프리뷰. 구현 수정 또는 기획 변경을 요청할 수 있다' },
    [...PLAN_EVENTS, ...BUILD_EVENTS, ...REVIEW_EVENTS,
      ['review_submitted', '검증 보고서 제출: 통과', { task_id: 't-validate', artifact_ids: ['a-validation'] }],
      ['review_submitted', '보안 보고서 제출: 통과', { task_id: 't-security', artifact_ids: ['a-security'] }],
      ['preview_ready', '격리 프리뷰 준비 (합성 예시에는 주소 없음)', { artifact_ids: ['a-preview'] }],
      ['run_state_changed', '프리뷰 확인 대기', {}],
    ],
    {
      state: 'preview_ready',
      tasks: buildTasks({ ...DONE_BUILD, 't-validate': 'succeeded', 't-security': 'succeeded' }),
      approvals: [PLAN_APPROVAL_DONE],
      reports: [report('validator', 'pass'), report('security', 'pass')],
      artifactIds: [...BUILD_ARTIFACTS, 'a-validation', 'a-security', 'a-preview'],
    },
  ),
  scenario(
    { id: 'release-approval', label: '배포 승인 대기', description: '커밋·이미지·환경·두 보고서·복구 계획이 묶인 대상. 이전 대상은 무효화됨' },
    [...PLAN_EVENTS, ...BUILD_EVENTS, ...REVIEW_EVENTS,
      ['review_submitted', '검증 보고서 제출: 통과', { task_id: 't-validate', artifact_ids: ['a-validation'] }],
      ['review_submitted', '보안 보고서 제출: 통과', { task_id: 't-security', artifact_ids: ['a-security'] }],
      ['approval_requested', '배포 승인 요청 (이전 후보)', {}],
      ['approval_invalidated', '환경 설정 변경으로 이전 배포 승인 대상 무효', {}],
      ['approval_requested', '배포 승인 요청 (현재 후보)', {}],
      ['run_state_changed', '배포 승인 대기', {}],
    ],
    {
      state: 'awaiting_release_approval',
      tasks: buildTasks({ ...DONE_BUILD, 't-validate': 'succeeded', 't-security': 'succeeded' }),
      approvals: [
        PLAN_APPROVAL_DONE,
        { id: 'ap-release-1', state: 'invalidated', target_digest: fakeDigest('d2'), target: { ...RELEASE_TARGET, environment_config_digest: fakeDigest('f0') } },
        { id: 'ap-release-2', state: 'pending', target_digest: fakeDigest('d3'), target: RELEASE_TARGET },
      ],
      reports: [report('validator', 'pass'), report('security', 'pass')],
      artifactIds: [...BUILD_ARTIFACTS, 'a-validation', 'a-security', 'a-preview'],
    },
    [],
    { 'env-staging': STAGING },
  ),
  scenario(
    { id: 'failed', label: '실패', description: '통합 단계 실패. 근거와 실패 이유를 보존한다' },
    [...PLAN_EVENTS, ...BUILD_EVENTS, ['task_finished', '통합 확인 실패 — 화면이 API 응답 형식과 불일치', { task_id: 't-int' }], ['run_state_changed', '실행 실패', {}]],
    {
      state: 'failed',
      reason: '통합 확인 실패: 응답 형식 불일치. 수정 요청 또는 새 실행이 필요합니다.',
      tasks: buildTasks({ 't-plan': 'succeeded', 't-contract': 'succeeded', 't-data': 'succeeded', 't-api': 'succeeded', 't-ui': 'succeeded', 't-int': { state: 'failed', reason: '응답 필드 status_label 누락' } }),
      approvals: [PLAN_APPROVAL_DONE],
      artifactIds: BUILD_ARTIFACTS,
    },
  ),
  scenario(
    { id: 'paused', label: '일시 중지', description: '사용자가 중지했다. 새 작업은 생기지 않으며 재개 전 최신 명세를 다시 확인한다' },
    [...PLAN_EVENTS, ...BUILD_EVENTS, ['run_state_changed', '사용자 요청으로 일시 중지', {}]],
    {
      state: 'paused',
      tasks: buildTasks({ 't-plan': 'succeeded', 't-contract': 'succeeded', 't-data': 'succeeded', 't-api': { state: 'pending', reason: '일시 중지로 대기' } }),
      approvals: [PLAN_APPROVAL_DONE],
      artifactIds: ['a-request', 'a-spec', 'a-contract', 'a-diff-data'],
    },
  ),
  scenario(
    { id: 'succeeded', label: '배포 완료', description: '승인된 이미지가 승인된 환경에 배포되고 상태 확인을 마쳤다' },
    [...PLAN_EVENTS, ...BUILD_EVENTS, ...REVIEW_EVENTS,
      ['review_submitted', '검증 보고서 제출: 통과', { task_id: 't-validate', artifact_ids: ['a-validation'] }],
      ['review_submitted', '보안 보고서 제출: 통과', { task_id: 't-security', artifact_ids: ['a-security'] }],
      ['approval_decided', '배포 승인', {}],
      ['deployment_started', '배포 시작 · env-staging', { task_id: 't-release' }],
      ['deployment_finished', '배포 완료 · 상태 확인 정상', { task_id: 't-release', artifact_ids: ['a-deploy'] }],
      ['run_state_changed', '완료', {}],
    ],
    {
      state: 'succeeded',
      tasks: buildTasks({ ...DONE_BUILD, 't-validate': 'succeeded', 't-security': 'succeeded', 't-release': 'succeeded' }),
      approvals: [PLAN_APPROVAL_DONE, { id: 'ap-release-2', state: 'approved', target_digest: fakeDigest('d3'), target: RELEASE_TARGET, decided_by: 'operator', decided_at: '2026-10-20T10:40:00+09:00' }],
      reports: [report('validator', 'pass'), report('security', 'pass')],
      artifactIds: [...BUILD_ARTIFACTS, 'a-validation', 'a-security', 'a-preview', 'a-deploy'],
    },
    [],
    { 'env-staging': STAGING },
  ),
]

export function findScenario(id: string | null): ExampleScenario | null {
  return SCENARIOS.find((s) => s.id === id) ?? null
}
