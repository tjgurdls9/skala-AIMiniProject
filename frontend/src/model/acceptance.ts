import type { AcceptanceItem, AcceptanceState, AcceptanceStatus } from '../api/types'
import type { StateLabel } from './labels'

export type AcView = AcceptanceState | 'unknown'

/** AC 판정 표시. 작업 완료 수와 별개이며, 판정이 없으면 '판정 없음'으로 둔다(충족으로 추정하지 않음) */
export const AC_STATE: Record<AcView, StateLabel> = {
  met: { text: '충족', glyph: '✓', tone: 'ok' },
  unmet: { text: '미충족', glyph: '○', tone: 'neutral' },
  failed: { text: '실패', glyph: '✕', tone: 'danger' },
  not_run: { text: '미실행', glyph: '–', tone: 'warn' },
  unknown: { text: '판정 없음', glyph: '?', tone: 'neutral' },
}

export function acIndex(status: AcceptanceStatus | null): Map<string, AcceptanceItem> {
  return new Map((status?.items ?? []).map((item) => [item.id, item]))
}

export function acView(index: ReadonlyMap<string, AcceptanceItem>, id: string): { state: AcView; reportId?: string } {
  const item = index.get(id)
  return item ? { state: item.status, reportId: item.report_id } : { state: 'unknown' }
}

export function tallyAc(index: ReadonlyMap<string, AcceptanceItem>, ids: readonly string[]): Record<AcView, number> {
  const tally: Record<AcView, number> = { met: 0, unmet: 0, failed: 0, not_run: 0, unknown: 0 }
  for (const id of ids) tally[acView(index, id).state] += 1
  return tally
}
