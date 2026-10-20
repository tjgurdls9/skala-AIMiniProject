import type { AcceptanceItem, AcceptanceState, AcceptanceStatus } from '../api/types'
import type { StateLabel } from './labels'

/** stale: 판정의 근거 보고서가 현재 회차에 없거나 근거 없는 충족 — 충족으로 표시하지 않는다(CT36) */
export type AcView = AcceptanceState | 'unknown' | 'stale'

/** AC 판정 표시. 작업 완료 수와 별개이며, 판정이 없으면 '판정 없음'으로 둔다(충족으로 추정하지 않음) */
export const AC_STATE: Record<AcView, StateLabel> = {
  met: { text: '충족', glyph: '✓', tone: 'ok' },
  unmet: { text: '미충족', glyph: '○', tone: 'neutral' },
  failed: { text: '실패', glyph: '✕', tone: 'danger' },
  not_run: { text: '미실행', glyph: '–', tone: 'warn' },
  unknown: { text: '판정 없음', glyph: '?', tone: 'neutral' },
  stale: { text: '근거 없음(무효)', glyph: '?', tone: 'warn' },
}

export function acIndex(status: AcceptanceStatus | null): Map<string, AcceptanceItem> {
  return new Map((status?.items ?? []).map((item) => [item.id, item]))
}

/**
 * 판정 하나를 화면 상태로. 근거 보고서 ID가 현재 스냅샷의 보고서에 없으면(회차가 바뀜) 무효,
 * 충족인데 근거 보고서가 없으면 확인할 수 없으므로 무효로 본다.
 */
export function acView(
  index: ReadonlyMap<string, AcceptanceItem>,
  id: string,
  reportIds: ReadonlySet<string>,
): { state: AcView; reportId?: string } {
  const item = index.get(id)
  if (!item) return { state: 'unknown' }
  if (item.report_id && !reportIds.has(item.report_id)) return { state: 'stale', reportId: item.report_id }
  if (item.status === 'met' && !item.report_id) return { state: 'stale' }
  return { state: item.status, reportId: item.report_id }
}

export function tallyAc(index: ReadonlyMap<string, AcceptanceItem>, ids: readonly string[], reportIds: ReadonlySet<string>): Record<AcView, number> {
  const tally: Record<AcView, number> = { met: 0, unmet: 0, failed: 0, not_run: 0, unknown: 0, stale: 0 }
  for (const id of ids) tally[acView(index, id, reportIds).state] += 1
  return tally
}
