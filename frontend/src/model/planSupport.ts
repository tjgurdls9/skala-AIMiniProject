import type { PlanView } from '../api/types'

// CR-C14 기획별 지원 공백(Claude 원래 번호). 계약: Codex a6eb8a4 PlanView.support(http.PlanSupport).

export type PlanSupport = NonNullable<PlanView['support']>
type Need = PlanSupport['external'][number]['needs'][number]
type ExternalStatus = PlanSupport['external'][number]['status']

const DIGEST = /^sha256:[a-f0-9]{64}$/
/** CR-C16: 서버가 시작 프로젝트 ID를 데이터로 준다. 특정 이름을 고정하지 않고 계약 패턴만 확인한다 */
const TEMPLATE_ID = /^[a-z0-9][a-z0-9-]{0,62}$/
const NEEDS = new Set<string>(['free_eligibility', 'key', 'quota', 'attribution', 'consent', 'isolation'])
const STATUSES = new Set<string>(['unconfirmed', 'confirmed', 'deferred'])

const isRecord = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v)
const isText = (v: unknown): v is string => typeof v === 'string' && v.length > 0

function isUnsupported(u: unknown): boolean {
  return isRecord(u) && isText(u.request_quote) && isText(u.reason) && Array.isArray(u.requires) && u.requires.every(isText)
}

function isExternal(e: unknown): boolean {
  return isRecord(e) && (e.provider === null || typeof e.provider === 'string') && isText(e.purpose) && isText(e.reason)
    && STATUSES.has(e.status as string)
    && Array.isArray(e.needs) && new Set(e.needs).size === e.needs.length && e.needs.every((n) => NEEDS.has(n as string))
}

/** http.PlanSupport 형태인지 확인한다. 화면이 열거 값으로 이름표를 조회하므로 원소까지 확인한다 */
export function isPlanSupport(value: unknown): value is PlanSupport {
  return isRecord(value) && typeof value.template_id === 'string' && TEMPLATE_ID.test(value.template_id) && isText(value.spec_version_id)
    && typeof value.request_digest === 'string' && DIGEST.test(value.request_digest)
    && typeof value.implementation_allowed === 'boolean'
    && Array.isArray(value.unsupported) && value.unsupported.every(isUnsupported)
    && Array.isArray(value.external) && value.external.every(isExternal)
}

/**
 * 승인 화면에서 지원 정보를 어떻게 다룰지.
 * - missing: 지원 정보가 없다. 지원 완료로 추정하지 않는다(옛 기록·옛 서버).
 * - mismatch: 다른 명세의 지원 정보다. 표시·승인을 막고 다시 읽는다.
 * - blocked: implementation_allowed=false. 승인은 막고 거절·수정 요청은 둔다.
 * - clear: 알려진 공백이 없다. AC 충족·검토·출시 수용이 아니다.
 */
export type SupportVerdict =
  | { kind: 'missing' }
  | { kind: 'mismatch'; specVersionId: string }
  | { kind: 'blocked' | 'clear'; support: PlanSupport }

export function supportVerdict(plan: PlanView): SupportVerdict {
  const support = plan.support
  if (!support) return { kind: 'missing' }
  if (support.spec_version_id !== plan.spec_version_id) return { kind: 'mismatch', specVersionId: support.spec_version_id }
  return { kind: support.implementation_allowed ? 'clear' : 'blocked', support }
}

// 템플릿은 이름을 붙이지 않고 서버 ID 그대로 보인다(과제 이름을 화면이 지어내지 않는다).
export const NEED_NAME: Record<Need, string> = {
  free_eligibility: '무료 자격',
  key: '키',
  quota: '쿼터',
  attribution: '출처 표시',
  consent: '사용자 동의',
  isolation: '격리 경로',
}

export const EXTERNAL_STATUS: Record<ExternalStatus, { text: string; tone: 'ok' | 'warn' | 'neutral' }> = {
  unconfirmed: { text: '미확인', tone: 'warn' },
  confirmed: { text: '확인됨', tone: 'ok' },
  deferred: { text: '보류(사용자 결정 대기)', tone: 'neutral' },
}
