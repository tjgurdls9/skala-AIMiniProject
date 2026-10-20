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

/** 사건이 현재 스냅샷보다 새 상태 버전을 가리키면 스냅샷을 다시 읽는다. 요약 문장으로 상태를 추측하지 않는다. */
export function needsSnapshot(snapshot: Pick<Snapshot, 'state_version'> | null, event: Pick<RunEvent, 'state_version'>): boolean {
  return snapshot === null || event.state_version > snapshot.state_version
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
