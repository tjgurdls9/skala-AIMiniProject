import type { Approval, PlanTarget, ReleaseTarget, ReviewReport, RunState, Snapshot, Sprint, Task } from '../api/types'

export interface SprintTally {
  total: number
  succeeded: number
  running: number
  failed: number
  blocked: number
  waiting: number
  closed: number
  acceptanceCount: number
}

const ACTIVE_RUN_STATES = new Set<RunState>([
  'planning', 'building', 'reviewing', 'deploying', 'waiting_resource', 'waiting_quota',
])

/** 정지·취소를 보낼 수 있는 실행 상태인가 (종료 상태 제외) */
export function isStoppable(state: RunState): boolean {
  return !['succeeded', 'failed', 'cancelled'].includes(state)
}

/**
 * 서버가 재개를 받는 상태(Codex c3e11c1 backend/store.py command(): resume 허용 상태).
 * 화면은 버튼만 보여주며 실제 가능 여부는 서버 응답(409 INVALID_STATE)이 최종 판단한다.
 */
export const RESUMABLE_STATES = new Set<RunState>(['paused', 'waiting_resource', 'waiting_quota', 'needs_input', 'failed'])

/** 서버가 명령을 받는 실행(종료된 succeeded·cancelled 제외) */
export function acceptsCommands(state: RunState): boolean {
  return state !== 'succeeded' && state !== 'cancelled'
}

export function isRunActive(state: RunState): boolean {
  return ACTIVE_RUN_STATES.has(state)
}

export function orderedPhases(snapshot: Snapshot): Snapshot['phases'] {
  return [...snapshot.phases].sort((a, b) => a.order - b.order)
}

export function sprintsOf(snapshot: Snapshot, phaseId: string): Sprint[] {
  return snapshot.sprints.filter((s) => s.phase_id === phaseId)
}

export function tasksOf(snapshot: Snapshot, sprintId: string): Task[] {
  return snapshot.tasks.filter((t) => t.sprint_id === sprintId)
}

/** 작업 수 집계. AC 충족은 계약에 없으므로 여기서 만들지 않는다(정의 개수만). */
export function tallySprint(snapshot: Snapshot, sprint: Sprint): SprintTally {
  const tasks = tasksOf(snapshot, sprint.id)
  const count = (states: Task['state'][]) => tasks.filter((t) => states.includes(t.state)).length
  return {
    total: tasks.filter((t) => t.state !== 'superseded').length,
    succeeded: count(['succeeded']),
    running: count(['running']),
    failed: count(['failed']),
    blocked: count(['blocked']),
    waiting: count(['pending', 'ready']),
    closed: count(['cancelled', 'superseded']),
    acceptanceCount: sprint.acceptance_ids.length,
  }
}

/**
 * 현재 Sprint는 서버 지정이 아니라 작업 상태에서 도출한다(CR-C08). Phase 순서를 따른다.
 * running → ready → 실패·차단 → 대기 순으로 찾고, 모두 끝났으면 마지막 Sprint.
 */
export function deriveCurrentSprintId(snapshot: Snapshot): string | null {
  const phaseRank = new Map(orderedPhases(snapshot).map((p, i) => [p.id, i]))
  const sprints = [...snapshot.sprints].sort(
    (a, b) => (phaseRank.get(a.phase_id) ?? 0) - (phaseRank.get(b.phase_id) ?? 0),
  )
  const priority: Task['state'][][] = [['running'], ['ready'], ['failed', 'blocked'], ['pending']]
  for (const states of priority) {
    const hit = sprints.find((s) => snapshot.tasks.some((t) => t.sprint_id === s.id && states.includes(t.state)))
    if (hit) return hit.id
  }
  return sprints.at(-1)?.id ?? null
}

/** 작업의 대기 이유: 서버 reason 우선, 없으면 끝나지 않은 선행 작업 */
export function waitingReason(task: Task, tasksById: ReadonlyMap<string, Task>): string | null {
  if (task.reason) return task.reason
  if (task.state !== 'pending' && task.state !== 'blocked') return null
  const open = task.depends_on
    .map((id) => tasksById.get(id))
    .filter((t): t is Task => !t || t.state !== 'succeeded')
  if (open.length === 0) return null
  return `선행 작업 대기: ${open.map((t) => t?.title ?? '알 수 없는 작업').join(', ')}`
}

export function indexById<T extends { id: string }>(items: readonly T[]): Map<string, T> {
  return new Map(items.map((item) => [item.id, item]))
}

export function pendingApproval(snapshot: Snapshot, gate: 'plan'): (Approval & { target: PlanTarget }) | null
export function pendingApproval(snapshot: Snapshot, gate: 'release'): (Approval & { target: ReleaseTarget }) | null
export function pendingApproval(snapshot: Snapshot, gate: 'plan' | 'release'): Approval | null {
  return snapshot.approvals.find((a) => a.state === 'pending' && a.target.gate === gate) ?? null
}

export interface ReviewPair {
  validator: ReviewReport | null
  security: ReviewReport | null
}

/** 배포 대상이 가리키는 두 보고서, 없으면 각 역할의 마지막 보고서. 한쪽 통과를 전체 통과로 합치지 않는다. */
export function reviewPair(snapshot: Snapshot, reportIds?: readonly string[]): ReviewPair {
  const pool = reportIds ? snapshot.reports.filter((r) => reportIds.includes(r.id)) : snapshot.reports
  const last = (role: ReviewReport['role']) => [...pool].reverse().find((r) => r.role === role) ?? null
  return { validator: last('validator'), security: last('security') }
}

export function bothPassed(pair: ReviewPair): boolean {
  return pair.validator?.verdict === 'pass' && pair.security?.verdict === 'pass'
}
