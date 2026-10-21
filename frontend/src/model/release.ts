import type { ReleaseView } from '../api/types'

// CR-C15 출시·복구 결과(Claude 원래 번호). 계약: Codex 8ff4ca1 → a6eb8a4(번호 정정·operation 근거 필드 추가).

type ReleaseState = ReleaseView['state']
type OperationState = ReleaseView['operations'][number]['state']
type Tone = 'ok' | 'warn' | 'danger' | 'neutral'

const DIGEST = /^sha256:[a-f0-9]{64}$/
const STATES = new Set<string>(['unconfigured', 'prepared', 'accepted', 'applied', 'uncertain', 'not_applied', 'superseded', 'rolled_back', 'failed'])
const ACTIONS = new Set<string>(['push', 'deploy', 'rollback'])
const OP_STATES = new Set<string>(['accepted', 'applied', 'uncertain', 'failed', 'rolled_back', 'not_applied', 'superseded'])
const isTimeOrNull = (v: unknown): boolean => v === null || (typeof v === 'string' && !Number.isNaN(Date.parse(v)))

const isRecord = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v)

/**
 * http.ReleaseView 형태인지 확인한다. 화면이 열거 값으로 이름표를 조회하므로 원소까지 확인한다.
 * enabled는 계약상 false 고정이다. true가 오면 계약 밖이므로 표시하지 않는다(실행 가능으로 오해하지 않게).
 */
export function isReleaseView(value: unknown): value is ReleaseView {
  if (!isRecord(value)) return false
  if (value.enabled !== false || !STATES.has(value.state as string)) return false
  if (typeof value.run_id !== 'string' || typeof value.reason !== 'string' || !value.reason) return false
  if (value.target !== null && !isRecord(value.target)) return false
  if (value.details !== null && !isRecord(value.details)) return false
  return Array.isArray(value.operations) && value.operations.every((o) =>
    isRecord(o) && typeof o.operation_id === 'string' && DIGEST.test(o.operation_id) && ACTIONS.has(o.action as string) && OP_STATES.has(o.state as string)
    && isTimeOrNull(o.accepted_at) && isTimeOrNull(o.observed_at) && typeof o.reason === 'string' && o.reason.length > 0
    && (o.volume_preserved === null || typeof o.volume_preserved === 'boolean'))
}

/** 마지막 공개 원장 결과의 요약. 의도 기록·확인된 결과·불명을 섞지 않는다 */
export const RELEASE_STATE: Record<ReleaseState, { text: string; tone: Tone; note?: string }> = {
  unconfigured: { text: '출시 대상 미설정', tone: 'neutral' },
  prepared: { text: '준비됨 · 실행하지 않음', tone: 'neutral' },
  accepted: { text: '실행 의도 기록 · 결과 미확인', tone: 'warn', note: '서버가 실행 의도만 기록했습니다. 완료로 보지 않습니다.' },
  applied: { text: '적용 확인됨', tone: 'ok', note: '어댑터가 실제 조회로 확인했던 결과입니다. 이 화면은 공급자를 다시 조회하지 않습니다.' },
  uncertain: { text: '결과 불명 · 자동 재실행 안 함', tone: 'danger', note: '응답 유실 등으로 결과를 확인하지 못했습니다. 성공으로 보지 않고 자동으로 다시 실행하지 않습니다.' },
  not_applied: { text: '적용 안 됨', tone: 'warn', note: '성공이 아닙니다.' },
  superseded: { text: '대체됨', tone: 'neutral', note: '더 새 대상으로 대체됐습니다. 성공이 아닙니다.' },
  rolled_back: { text: '첫 출시 공개 중단', tone: 'warn', note: '이 복구는 첫 출시 서비스의 공개를 멈춘 것입니다(계획: 데이터 볼륨 보존). 이전 버전 복원이 아닙니다. 볼륨 보존 여부는 작업별 조회 결과로만 확인합니다.' },
  failed: { text: '실패', tone: 'danger' },
}

export const OPERATION_ACTION: Record<ReleaseView['operations'][number]['action'], string> = {
  push: 'Git push',
  deploy: '배포',
  rollback: '복구(첫 출시 공개 중단)',
}

/** 원장 단위 상태. accepted는 의도 기록, uncertain은 불명, 나머지는 확인된 결과(성공은 applied·rolled_back뿐) */
export const OPERATION_STATE: Record<OperationState, { text: string; group: string; tone: Tone }> = {
  accepted: { text: '의도 기록', group: '의도 기록', tone: 'warn' },
  applied: { text: '적용 확인', group: '확인된 결과', tone: 'ok' },
  rolled_back: { text: '공개 중단 확인', group: '확인된 결과', tone: 'warn' },
  failed: { text: '실패', group: '확인된 결과', tone: 'danger' },
  not_applied: { text: '적용 안 됨', group: '확인된 결과', tone: 'warn' },
  superseded: { text: '대체됨', group: '확인된 결과', tone: 'neutral' },
  uncertain: { text: '불명', group: '불명', tone: 'danger' },
}

/** 볼륨 보존 조회 결과. null은 미확인이며 보존으로 추정하지 않는다. true도 데이터 내용·DB 이전 검증이 아니다 */
export function volumeText(value: boolean | null): string {
  if (value === null) return '볼륨 보존 미확인'
  return value ? '볼륨 보존 조회 확인(데이터 내용 검증 아님)' : '볼륨 보존 안 됨'
}
