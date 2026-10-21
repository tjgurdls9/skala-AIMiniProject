import type { RunEvent, Snapshot } from '../api/types'

export type Ingest =
  | { kind: 'append' }
  | { kind: 'duplicate' }
  | { kind: 'gap'; expected: number; got: number }

/** 실행별 연속 seq 기준으로 새 사건을 판정한다. 중복은 버리고 누락은 재동기화한다. */
export function classifyEvent(lastSeq: number, event: Pick<RunEvent, 'seq'>): Ingest {
  if (event.seq <= lastSeq) return { kind: 'duplicate' }
  if (event.seq !== lastSeq + 1) return { kind: 'gap', expected: lastSeq + 1, got: event.seq }
  return { kind: 'append' }
}

/**
 * 스냅샷 이후의 사건이면 스냅샷을 다시 읽는다. 요약 문장으로 상태를 추측하지 않는다.
 * 같은 state_version에도 사건이 여러 개 있을 수 있고(계약 §3), 서버는 그 사건으로 작업 상태·근거 아티팩트를 바꾼다.
 * 그래서 버전이 아니라 스냅샷이 반영한 마지막 seq와 비교한다.
 */
export function needsSnapshot(snapshot: Pick<Snapshot, 'last_event_seq'> | null, event: Pick<RunEvent, 'seq'>): boolean {
  return snapshot === null || event.seq > snapshot.last_event_seq
}

/** 늦게 도착한 옛 스냅샷인지(버전이 낮거나, 같은 버전에서 더 이른 사건까지만 반영) */
export function isOlderSnapshot(next: Pick<Snapshot, 'state_version' | 'last_event_seq'>, current: Pick<Snapshot, 'state_version' | 'last_event_seq'>): boolean {
  return next.state_version < current.state_version
    || (next.state_version === current.state_version && next.last_event_seq < current.last_event_seq)
}

/** SSE data 문자열을 protocol.Event로 최소 검증한다. 형식이 다르면 null. */
export function parseEventData(data: string, runId: string): RunEvent | null {
  let value: unknown
  try {
    value = JSON.parse(data)
  } catch {
    return null
  }
  const e = value as Partial<RunEvent> | null
  if (!e || e.kind !== 'event' || e.run_id !== runId) return null
  if (!Number.isInteger(e.seq) || (e.seq as number) < 1) return null
  if (!Number.isInteger(e.state_version) || typeof e.event_type !== 'string') return null
  if (typeof e.summary !== 'string' || !Array.isArray(e.artifact_ids)) return null
  return e as RunEvent
}
