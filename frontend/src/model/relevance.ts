import type { RunEvent, Task, WorkKind } from '../api/types'
import { ALWAYS_SHOWN_EVENTS, CRITICAL_EVENTS } from './labels'

/**
 * 로컬 관련도 보조: 서버가 준 작업 분야(work_kind)와 의존 관계만 사용한다.
 * 모델·임베딩 호출 없음. 정렬을 바꾸지 않고 강조만 한다. 승인·보안·AC 판정에 쓰지 않는다.
 */
export function relatedTaskIds(tasks: readonly Task[], interests: ReadonlySet<WorkKind>): Set<string> {
  const direct = new Set(tasks.filter((t) => interests.has(t.work_kind)).map((t) => t.id))
  const related = new Set(direct)
  for (const t of tasks) {
    if (t.depends_on.some((id) => direct.has(id))) related.add(t.id)
    if (direct.has(t.id)) t.depends_on.forEach((id) => related.add(id))
  }
  return related
}

export type Emphasis = 'critical' | 'related' | 'none'

export function eventEmphasis(event: RunEvent, related: ReadonlySet<string>): Emphasis {
  if (CRITICAL_EVENTS.has(event.event_type)) return 'critical'
  if (event.task_id && related.has(event.task_id)) return 'related'
  return 'none'
}

/** "강조 항목만" 필터에서도 남길 사건: 강조 대상 + 실패·판정·상태 전이 유형 */
export function keepWhenFiltered(event: RunEvent, related: ReadonlySet<string>): boolean {
  return ALWAYS_SHOWN_EVENTS.has(event.event_type) || eventEmphasis(event, related) !== 'none'
}

export interface EventGroup {
  key: string
  first: RunEvent
  last: RunEvent
  count: number
}

/** 연속된 같은 종류·같은 작업의 근거 사건만 묶는다(순서 유지). 판정·상태 전이 사건은 묶지 않는다. */
export function groupRepeats(events: readonly RunEvent[]): EventGroup[] {
  const groups: EventGroup[] = []
  for (const e of events) {
    const prev = groups.at(-1)
    if (prev && prev.last.event_type === e.event_type && prev.last.task_id === e.task_id && !ALWAYS_SHOWN_EVENTS.has(e.event_type)) {
      groups[groups.length - 1] = { ...prev, last: e, count: prev.count + 1 }
    } else {
      groups.push({ key: String(e.seq), first: e, last: e, count: 1 })
    }
  }
  return groups
}
