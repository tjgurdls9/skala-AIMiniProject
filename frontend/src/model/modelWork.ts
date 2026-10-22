import type { RunState, Snapshot } from '../api/types'
import { RUN_STATE } from './labels'

/**
 * 로컬 모델이 한 단계를 처리하는 동안은 사건이 오래 없을 수 있다(수십 초~수 분).
 * 서버가 알려 주는 "모델 작업 단계" 상태에서만 대기 표시를 보인다. 진행률·남은 시간은 계약에 없어 만들지 않는다.
 * 승인 대기·입력 필요·중지·실패·자원/한도 대기·배포는 각자의 결정·알림 UI가 있으므로 제외한다.
 */
const MODEL_WORK_STATES: ReadonlySet<RunState> = new Set<RunState>(['planning', 'building', 'reviewing'])

/** 서버 시각이 이 범위를 벗어나면(합성 예시·시계 어긋남) 화면이 사건을 받은 시각을 쓴다 */
const MAX_AGE_MS = 24 * 60 * 60 * 1000
const CLOCK_SKEW_MS = 5000

export interface ModelWork {
  stage: string
  running: string[]
}

export function modelWork(snapshot: Snapshot): ModelWork | null {
  if (!MODEL_WORK_STATES.has(snapshot.state)) return null
  return {
    stage: RUN_STATE[snapshot.state].text,
    running: snapshot.tasks.filter((t) => t.state === 'running').map((t) => t.title),
  }
}

/** 마지막 사건 이후 경과 초. 서버 시각을 믿을 수 있으면 그것을, 아니면 화면이 사건을 받은 시각을 쓴다 */
export function idleSeconds(lastOccurredAt: string | undefined, receivedAtMs: number, nowMs: number): number {
  const server = lastOccurredAt ? Date.parse(lastOccurredAt) : Number.NaN
  const age = nowMs - server
  const base = Number.isFinite(server) && age >= -CLOCK_SKEW_MS && age <= MAX_AGE_MS ? age : nowMs - receivedAtMs
  return Math.max(0, Math.floor(base / 1000))
}

export function formatIdle(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  if (h > 0) return m > 0 ? `${h}시간 ${m}분` : `${h}시간`
  if (m > 0) return s > 0 ? `${m}분 ${s}초` : `${m}분`
  return `${s}초`
}
