// 합성 전체 과정 시연 — 요청 → 기획 승인 → 층별 구현 → 검증·보안 → 프리뷰 → 사람 확인 → 배포 승인 대상.
// 실제 모델 실행이 아니다. 같은 사무실 UI에 단계별 합성 스냅샷과 사건을 흘려 줄 뿐이며 서버로는 아무것도 보내지 않는다.
import { ApiError } from '../api/errors'
import type { DemoControl, DemoInfo, RunSource, StreamHandlers } from '../api/source'
import type { Approval, Command, CommandReceipt, RunEvent, Snapshot } from '../api/types'
import { PLAN_APPROVAL_DONE, PLAN_APPROVAL_PENDING, RUN_ID, buildEvents, buildSnapshot, buildTasks, fakeDigest, report, type TaskStateMap } from './base'
import { exampleSource } from './exampleSource'
import {
  ACCEPTANCE_APPROVED, ACCEPTANCE_PENDING, RELEASES, RELEASE_TARGET, STAGING, SCENARIOS, WITH_MANUAL,
  acceptanceOf, type ExampleScenario, type Seeds,
} from './scenarios'

export const FULL_CYCLE_ID = 'full-cycle'
export const FULL_CYCLE_BADGE = '합성 시연 · 실제 모델 실행 아님'

type Gate = 'plan' | 'acceptance'

export interface DemoStage extends ExampleScenario {
  /** 이 단계가 끝날 때까지 보낸 사건 수 */
  end: number
  /** 사람이 결정해야 다음으로 넘어가는 단계 */
  gate?: Gate
}

export interface FullCycle {
  events: RunEvent[]
  initial: ExampleScenario
  stages: DemoStage[]
}

const SPRINT_PLAN = { task_id: 't-plan', sprint_id: 'sp-1' }

/** 단계 경계마다 [사건들]을 묶는다. 결과를 말하는 사건에는 합성 표시를 붙인다 */
const STAGE_SEEDS: Array<{ id: string; label: string; seeds: Seeds }> = [
  { id: 'request', label: '요청 접수', seeds: [
    ['run_state_changed', '실행 시작 · 요청 접수 (합성 시연)', {}],
    ['task_started', '요청 분석 시작', SPRINT_PLAN],
  ] },
  { id: 'plan-writing', label: '기획안 작성', seeds: [
    ['retrieval_finished', '기획 양식·템플릿 문서 3건 검색 (합성)', SPRINT_PLAN],
    ['context_saved', '요청 원문을 문맥 패킷에 저장', SPRINT_PLAN],
    ['task_finished', '기획안 v1 작성 완료', { ...SPRINT_PLAN, artifact_ids: ['a-spec'] }],
  ] },
  { id: 'plan-approval', label: '기획 승인 대기', seeds: [
    ['plan_proposed', '기획안 v1 제시 · 대안 2개, 작업 분해, AC별 점검', { artifact_ids: ['a-spec'] }],
    ['approval_requested', '기획 승인 요청 · 승인 전에는 구현을 시작하지 않음', {}],
    ['run_state_changed', '기획 승인 대기', {}],
  ] },
  { id: 'build-start', label: '구현 시작 · API 계약', seeds: [
    ['approval_decided', '기획 v1 승인', {}],
    ['run_state_changed', '구현 단계 시작', {}],
    ['task_started', 'API 계약 정의 시작', { task_id: 't-contract', sprint_id: 'sp-2' }],
  ] },
  { id: 'build-parallel', label: '데이터·API 구현', seeds: [
    ['task_finished', 'API 계약 정의 완료', { task_id: 't-contract', sprint_id: 'sp-2', artifact_ids: ['a-contract'] }],
    ['task_started', '데이터 적재 시작', { task_id: 't-data', sprint_id: 'sp-2' }],
    ['task_started', 'API 구현 시작', { task_id: 't-api', sprint_id: 'sp-2' }],
  ] },
  { id: 'build-tests', label: '데이터·API 점검', seeds: [
    ['tool_finished', '데이터 적재 테스트 통과 (합성)', { task_id: 't-data', sprint_id: 'sp-2', artifact_ids: ['a-diff-data'] }],
    ['task_finished', '데이터 적재 완료', { task_id: 't-data', sprint_id: 'sp-2' }],
    ['tool_finished', 'API 테스트 12건 통과 (합성 수치)', { task_id: 't-api', sprint_id: 'sp-2', artifact_ids: ['a-test-api', 'a-diff-api'] }],
    ['task_finished', 'API 구현 완료', { task_id: 't-api', sprint_id: 'sp-2' }],
  ] },
  { id: 'build-ui', label: '화면 구현', seeds: [
    ['task_started', '컨테이너 이미지 빌드 구성 시작', { task_id: 't-infra', sprint_id: 'sp-2' }],
    ['task_started', '화면 구현 시작', { task_id: 't-ui', sprint_id: 'sp-3' }],
    ['tool_finished', '화면 변경 적용 (합성)', { task_id: 't-ui', sprint_id: 'sp-3', artifact_ids: ['a-diff-ui'] }],
  ] },
  { id: 'integrate', label: '통합·후보 빌드', seeds: [
    ['task_finished', '컨테이너 이미지 빌드 구성 완료', { task_id: 't-infra', sprint_id: 'sp-2' }],
    ['task_finished', '화면 구현 완료', { task_id: 't-ui', sprint_id: 'sp-3' }],
    ['task_started', '통합 확인 시작', { task_id: 't-int', sprint_id: 'sp-3' }],
    ['task_finished', '통합·후보 이미지 빌드 완료 (합성)', { task_id: 't-int', sprint_id: 'sp-3', artifact_ids: ['a-build'] }],
  ] },
  { id: 'review-start', label: '독립 검토 시작', seeds: [
    ['run_state_changed', '독립 검토 시작 · 같은 후보 커밋', {}],
    ['task_started', '기능 검증 시작', { task_id: 't-validate', sprint_id: 'sp-4' }],
    ['task_started', '보안 점검 시작', { task_id: 't-security', sprint_id: 'sp-4' }],
  ] },
  { id: 'review-done', label: '검증·보안 보고서', seeds: [
    ['review_submitted', '검증 보고서 제출: 통과 (합성)', { task_id: 't-validate', sprint_id: 'sp-4', artifact_ids: ['a-validation'] }],
    ['review_submitted', '보안 보고서 제출: 통과 (합성)', { task_id: 't-security', sprint_id: 'sp-4', artifact_ids: ['a-security'] }],
  ] },
  { id: 'preview', label: '프리뷰 · 사람 확인 대기', seeds: [
    ['preview_ready', '격리 프리뷰 준비 (합성 시연에는 주소 없음)', { artifact_ids: ['a-preview'] }],
    ['approval_requested', '사람 확인 승인 요청 · AC-4 (자동 점검 없는 화면 확인)', {}],
    ['run_state_changed', '프리뷰 확인 대기', {}],
  ] },
  { id: 'release-target', label: '배포 승인 대상', seeds: [
    ['approval_decided', '사람 확인 승인 · AC-4', {}],
    ['approval_requested', '배포 승인 요청 (현재 후보)', {}],
    ['run_state_changed', '배포 승인 대기', {}],
  ] },
]

const GATES: Record<string, Gate> = { 'plan-approval': 'plan', preview: 'acceptance' }
/** 이 단계의 첫 사건이 사람 결정의 반영이다(결정 명령 id를 담아 화면의 대기 표시를 푼다) */
const DECIDED_STAGES = new Set(['build-start', 'release-target'])

const RELEASE_PENDING: Approval = { id: 'ap-release-2', state: 'pending', target_digest: fakeDigest('d3'), target: RELEASE_TARGET }

const A_PLAN = ['a-request', 'a-spec', 'a-context-plan']
const A_API = [...A_PLAN, 'a-contract']
const A_DATA = [...A_API, 'a-diff-data', 'a-retrieval-api', 'a-test-api', 'a-diff-api']
const A_UI = [...A_DATA, 'a-diff-ui', 'a-build']
const A_REVIEW = [...A_UI, 'a-validation', 'a-security']
const A_PREVIEW = [...A_REVIEW, 'a-preview']

const DONE_PLAN: TaskStateMap = { 't-plan': 'succeeded' }
const DONE_API: TaskStateMap = { ...DONE_PLAN, 't-contract': 'succeeded' }
const DONE_DATA: TaskStateMap = { ...DONE_API, 't-data': 'succeeded', 't-api': 'succeeded' }
const DONE_BUILD: TaskStateMap = { ...DONE_DATA, 't-infra': 'succeeded', 't-ui': 'succeeded', 't-int': 'succeeded' }
const DONE_REVIEW: TaskStateMap = { ...DONE_BUILD, 't-validate': 'succeeded', 't-security': 'succeeded' }

type StageView = Pick<Parameters<typeof buildSnapshot>[0], 'state' | 'tasks' | 'approvals' | 'reports' | 'artifactIds'>
const REPORTS = [report('validator', 'pass'), report('security', 'pass')]

/** 단계별 화면 상태. STAGE_SEEDS와 같은 순서 */
const STAGE_VIEWS: StageView[] = [
  { state: 'planning', tasks: buildTasks({ 't-plan': 'running' }), artifactIds: ['a-request'] },
  { state: 'planning', tasks: buildTasks(DONE_PLAN), artifactIds: A_PLAN },
  { state: 'awaiting_plan_approval', tasks: buildTasks(DONE_PLAN), approvals: [PLAN_APPROVAL_PENDING], artifactIds: A_PLAN },
  { state: 'building', tasks: buildTasks({ ...DONE_PLAN, 't-contract': 'running' }), approvals: [PLAN_APPROVAL_DONE], artifactIds: A_PLAN },
  { state: 'building', tasks: buildTasks({ ...DONE_API, 't-data': 'running', 't-api': 'running' }), approvals: [PLAN_APPROVAL_DONE], artifactIds: A_API },
  { state: 'building', tasks: buildTasks(DONE_DATA), approvals: [PLAN_APPROVAL_DONE], artifactIds: A_DATA },
  { state: 'building', tasks: buildTasks({ ...DONE_DATA, 't-infra': 'running', 't-ui': 'running' }), approvals: [PLAN_APPROVAL_DONE], artifactIds: A_DATA },
  { state: 'building', tasks: buildTasks(DONE_BUILD), approvals: [PLAN_APPROVAL_DONE], artifactIds: A_UI },
  { state: 'reviewing', tasks: buildTasks({ ...DONE_BUILD, 't-validate': 'running', 't-security': 'running' }), approvals: [PLAN_APPROVAL_DONE], artifactIds: A_UI },
  { state: 'reviewing', tasks: buildTasks(DONE_REVIEW), approvals: [PLAN_APPROVAL_DONE], reports: REPORTS, artifactIds: A_REVIEW },
  { state: 'preview_ready', tasks: buildTasks(DONE_REVIEW), approvals: [PLAN_APPROVAL_DONE, ACCEPTANCE_PENDING], reports: REPORTS, artifactIds: A_PREVIEW },
  { state: 'awaiting_release_approval', tasks: buildTasks(DONE_REVIEW), approvals: [PLAN_APPROVAL_DONE, ACCEPTANCE_APPROVED, RELEASE_PENDING], reports: REPORTS, artifactIds: A_PREVIEW },
]

/** 검증 통과 단계부터 사람 확인 AC만 미실행으로 남고 나머지 기능 AC는 충족이다 */
const REVIEWED_FROM = STAGE_SEEDS.findIndex((s) => s.id === 'review-done')

export function buildFullCycle(): FullCycle {
  const seeds = STAGE_SEEDS.flatMap((s) => s.seeds)
  const events = buildEvents(seeds)
  const bodies = SCENARIOS.find((s) => s.id === 'preview')!.artifactBodies
  const base = { events: [], tail: [], artifactBodies: bodies, environments: { 'env-staging': STAGING } }

  const initial: ExampleScenario = {
    ...base, id: `${FULL_CYCLE_ID}-initial`, label: '시작 전', description: '요청 접수 전',
    snapshot: buildSnapshot({ state: 'planning', stateVersion: 0, lastSeq: 0, tasks: buildTasks({}), artifactIds: ['a-request'] }),
    acceptance: acceptanceOf({}),
  }

  let end = 0
  const stages = STAGE_SEEDS.map((stage, i): DemoStage => {
    end += stage.seeds.length
    const last = events[end - 1]!
    const view = STAGE_VIEWS[i]!
    const gate = GATES[stage.id]
    return {
      ...base,
      id: stage.id,
      label: stage.label,
      description: stage.label,
      end,
      ...(gate ? { gate } : {}),
      snapshot: buildSnapshot({ ...view, stateVersion: last.state_version, lastSeq: last.seq }),
      acceptance: i >= REVIEWED_FROM ? acceptanceOf(WITH_MANUAL, 'rp-validator') : acceptanceOf({}),
      ...(i === STAGE_SEEDS.length - 1 ? { release: RELEASES['release-approval'] } : {}),
    }
  })
  return { events, initial, stages }
}

export interface FullCycleTiming {
  /** 연결 뒤 첫 사건까지(시작 화면에서 사무실로 열리는 전환을 기다린다) */
  startDelayMs: number
  /** 한 단계 안의 사건 간격 */
  eventGapMs: number
  /** 단계가 끝난 뒤 다음 단계까지(엘리베이터·장면 연출을 볼 시간) */
  stagePauseMs: number
}

export const DEFAULT_TIMING: FullCycleTiming = { startDelayMs: 1500, eventGapMs: 1100, stagePauseMs: 2200 }
/** 결정 명령을 받은 뒤 반영 사건을 보내기까지(접수 응답이 먼저 돌아가게) */
const DECISION_APPLY_MS = 300

const noop = (message: string): ApiError => new ApiError(0, 'EXAMPLE_NOOP', message)

export function fullCycleSource(timing: Partial<FullCycleTiming> = {}): RunSource & { demo: DemoControl } {
  const { startDelayMs, eventGapMs, stagePauseMs } = { ...DEFAULT_TIMING, ...timing }
  const { events, initial, stages } = buildFullCycle()

  /** 스냅샷에 반영된 마지막 단계(-1이면 시작 전)와 지금까지 보낸 사건 수 */
  let stage = -1
  let emitted = 0
  let held: Gate | null = null
  let handlers: StreamHandlers | null = null
  let timer: ReturnType<typeof setTimeout> | null = null
  let decisionCommandId: string | null = null
  const listeners = new Set<() => void>()

  const current = (): ExampleScenario => (stage < 0 ? initial : stages[stage]!)
  const notify = (): void => listeners.forEach((fn) => fn())

  function clearTimer(): void {
    if (timer) clearTimeout(timer)
    timer = null
  }

  function schedule(delay: number): void {
    clearTimer()
    timer = setTimeout(tick, delay)
  }

  /** 다음 사건 하나를 보낸다. 단계의 마지막 사건이면 그 전에 스냅샷을 올려 화면이 새 상태를 읽게 한다 */
  function tick(): void {
    timer = null
    const target = stages[stage + 1]
    if (!handlers || !target || held) return
    let event: RunEvent = events[emitted]!
    emitted += 1
    if (decisionCommandId && DECIDED_STAGES.has(target.id) && emitted === target.end - (STAGE_SEEDS[stage + 1]!.seeds.length - 1)) {
      event = { ...event, command_id: decisionCommandId }
      decisionCommandId = null
    }
    const finished = emitted === target.end
    if (finished) stage += 1
    handlers.onEvent(event)
    notify()
    if (!finished) return schedule(eventGapMs)
    if (target.gate) {
      held = target.gate
      notify()
    } else if (stage + 1 < stages.length) schedule(stagePauseMs)
  }

  const demo: DemoControl = {
    badge: FULL_CYCLE_BADGE,
    info(): DemoInfo {
      return { index: stage, total: stages.length, label: stage < 0 ? '시작 전' : stages[stage]!.label, waiting: held, done: stage === stages.length - 1 }
    },
    onChange(fn) {
      listeners.add(fn)
      return () => listeners.delete(fn)
    },
    next() {
      if (held || !handlers) return
      clearTimer()
      tick()
    },
  }

  return {
    kind: 'example',
    runId: RUN_ID,
    demo,
    getSnapshot: async (): Promise<Snapshot> => current().snapshot,
    getAcceptance: async () => current().acceptance,
    getRecording: () => exampleSource(current()).getRecording(),
    getRelease: () => exampleSource(current()).getRelease(),
    getArtifact: (id) => exampleSource(current()).getArtifact(id),
    getEnvironment: (id) => exampleSource(current()).getEnvironment(id),
    openEvents(afterSeq, next) {
      handlers = next
      const opening = setTimeout(() => {
        next.onOpen()
        events.slice(afterSeq, emitted).forEach((e) => next.onEvent(e))
        if (!timer && !held && stage + 1 < stages.length) schedule(emitted === 0 ? startDelayMs : eventGapMs)
      }, 0)
      return () => {
        clearTimeout(opening)
        clearTimer()
        if (handlers === next) handlers = null
      }
    },
    async sendCommand(command: Command): Promise<CommandReceipt> {
      if (command.action !== 'decide') throw noop('합성 시연에서는 승인만 진행합니다. 다른 명령은 보내지 않습니다.')
      const { approval_id: approvalId, target_digest: digest, decision } = command.payload
      const pending = current().snapshot.approvals.find((a) => a.state === 'pending' && a.id === approvalId)
      if (!held || !pending || pending.target_digest !== digest) throw noop('합성 시연에서 지금 승인할 수 있는 대상이 아닙니다.')
      if (decision !== 'approve') throw noop('합성 시연에서는 승인만 진행합니다. 거절·수정 요청은 보내지 않습니다.')
      held = null
      decisionCommandId = command.command_id
      schedule(DECISION_APPLY_MS)
      notify()
      return { command_id: command.command_id, run_id: RUN_ID, status: 'accepted', accepted_at: new Date().toISOString() }
    },
  }
}
