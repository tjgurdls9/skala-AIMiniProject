import type { PlanView } from '../api/types'

// CR-C17(계약 76147c6): PlanView 확장 필드(대안·작업 분해·점검·의존성). 모두 선택이고, 없으면 "미제공·미확인"이다.

export type PlanAlternative = NonNullable<PlanView['alternatives']>[number]
export type WorkItem = NonNullable<PlanView['work_plan']>[number]
export type OmittedArea = NonNullable<PlanView['omitted_areas']>[number]
export type CheckSpec = NonNullable<PlanView['verification']>[number]
export type ManualAcceptance = NonNullable<PlanView['manual_acceptance']>[number]
type Ac = PlanView['acceptance'][number]

const ID = /^[A-Za-z0-9_-]{1,40}$/
const DIGEST = /^sha256:[a-f0-9]{64}$/
const WORK_KINDS = new Set(['contract', 'infra', 'backend', 'frontend', 'ai_data', 'integration'])
const OMITTED_KINDS = new Set(['infra', 'backend', 'frontend', 'ai_data'])
const METHODS = new Set(['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])

const isRecord = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v)
const isText = (v: unknown, max = 4000): v is string => typeof v === 'string' && v.length > 0 && v.length <= max
const isId = (v: unknown): v is string => typeof v === 'string' && ID.test(v)
const onlyKeys = (v: Record<string, unknown>, keys: readonly string[]): boolean => Object.keys(v).every((k) => keys.includes(k))
const isList = (v: unknown, min: number, max: number): v is unknown[] => Array.isArray(v) && v.length >= min && v.length <= max
const isUniqueTexts = (v: unknown, min: number, max: number, itemMax = 4000): boolean =>
  isList(v, min, max) && v.every((x) => isText(x, itemMax)) && new Set(v).size === v.length
const isUniqueIds = (v: unknown, max: number): boolean => isList(v, 0, max) && v.every(isId) && new Set(v).size === v.length

const isAlternative = (v: unknown): boolean =>
  isRecord(v) && onlyKeys(v, ['id', 'summary', 'differences', 'risks']) && isId(v.id) && isText(v.summary, 2000) && isText(v.differences, 2000) && isText(v.risks, 2000)

const isWorkItem = (v: unknown): boolean =>
  isRecord(v) && onlyKeys(v, ['id', 'kind', 'title', 'depends_on', 'acceptance_ids', 'write_scope'])
  && isId(v.id) && WORK_KINDS.has(v.kind as string) && isText(v.title, 500)
  && isUniqueIds(v.depends_on, 30) && isUniqueTexts(v.acceptance_ids, 1, 50) && isUniqueTexts(v.write_scope, 1, 20, 200)

const isOmitted = (v: unknown): boolean => isRecord(v) && onlyKeys(v, ['kind', 'reason']) && OMITTED_KINDS.has(v.kind as string) && isText(v.reason, 2000)
const isManual = (v: unknown): boolean => isRecord(v) && onlyKeys(v, ['ac_id', 'reason']) && isText(v.ac_id) && isText(v.reason, 2000)

function isHttpStep(v: unknown): boolean {
  if (!isRecord(v) || !onlyKeys(v, ['method', 'path', 'json', 'expect'])) return false
  if (!METHODS.has(v.method as string) || typeof v.path !== 'string' || !/^\/\S{0,200}$/.test(v.path)) return false
  if (v.json !== undefined && !isRecord(v.json)) return false
  const e = v.expect
  return isRecord(e) && onlyKeys(e, ['status', 'json_subset']) && Number.isInteger(e.status) && (e.status as number) >= 100 && (e.status as number) <= 599
}

function isCheckSpec(v: unknown): boolean {
  if (!isRecord(v) || !isId(v.id) || !isUniqueTexts(v.ac_ids, 1, 50)) return false
  const e = v.expect
  switch (v.kind) {
    case 'http':
      return onlyKeys(v, ['id', 'ac_ids', 'kind', 'steps']) && isList(v.steps, 1, 10) && v.steps.every(isHttpStep)
    case 'command':
      return onlyKeys(v, ['id', 'ac_ids', 'kind', 'argv', 'cwd', 'expect'])
        && isList(v.argv, 1, 32) && v.argv.every((a) => typeof a === 'string' && a.length <= 500)
        && (v.cwd === undefined || isText(v.cwd, 200))
        && isRecord(e) && onlyKeys(e, ['exit', 'stdout_contains']) && Number.isInteger(e.exit) && (e.exit as number) >= 0 && (e.exit as number) <= 255
        && (e.stdout_contains === undefined || (isList(e.stdout_contains, 0, 20) && e.stdout_contains.every((x) => isText(x, 500))))
    case 'file':
      return onlyKeys(v, ['id', 'ac_ids', 'kind', 'path', 'expect'])
        && isText(v.path, 200)
        && isRecord(e) && onlyKeys(e, ['exists', 'contains']) && typeof e.exists === 'boolean'
        && (e.contains === undefined || (isList(e.contains, 0, 20) && e.contains.every((x) => isText(x, 500))))
    default:
      return false
  }
}

function isDependencies(v: unknown): boolean {
  if (!isRecord(v) || !onlyKeys(v, ['pip', 'npm'])) return false
  return (['pip', 'npm'] as const).every((k) => v[k] === undefined || isUniqueTexts(v[k], 0, 20, 100))
}

/** 확장 필드가 있으면 계약 형식이어야 한다. 하나라도 어긋나면 기획 본문 전체를 형식 오류로 본다 */
export function isPlanExtras(plan: Partial<PlanView>): boolean {
  const alternatives = plan.alternatives
  if (alternatives !== undefined && !(isList(alternatives, 1, 3) && alternatives.every(isAlternative))) return false
  if (plan.selected_alternative_id !== undefined) {
    if (!isId(plan.selected_alternative_id)) return false
    // 선택된 대안은 대안 목록 안에 있어야 한다(없으면 어느 대안을 구현하는지 알 수 없다)
    if (alternatives !== undefined && !alternatives.some((a) => a.id === plan.selected_alternative_id)) return false
  }
  if (plan.single_alternative_reason !== undefined && !isText(plan.single_alternative_reason, 2000)) return false
  if (plan.work_plan !== undefined && !(isList(plan.work_plan, 0, 30) && plan.work_plan.every(isWorkItem))) return false
  if (plan.omitted_areas !== undefined && !(isList(plan.omitted_areas, 0, 4) && plan.omitted_areas.every(isOmitted))) return false
  if (plan.verification !== undefined && !(isList(plan.verification, 0, 100) && plan.verification.every(isCheckSpec))) return false
  if (plan.manual_acceptance !== undefined && !(isList(plan.manual_acceptance, 0, 50) && plan.manual_acceptance.every(isManual))) return false
  if (plan.dependencies !== undefined && !isDependencies(plan.dependencies)) return false
  if (plan.tool_policy_digest !== undefined && !(typeof plan.tool_policy_digest === 'string' && DIGEST.test(plan.tool_policy_digest))) return false
  return true
}

export interface AcRow {
  ac: Ac
  checks: CheckSpec[]
  manual: ManualAcceptance | null
  /** 점검도 사람 확인도 연결되지 않은 AC */
  uncovered: boolean
}

export type AcCoverage = { kind: 'missing' } | { kind: 'known'; rows: AcRow[]; uncoveredCount: number }

/**
 * AC별로 연결된 점검(verification)과 사람 확인(manual_acceptance)을 모은다.
 * 둘 다 필드가 없으면 옛 기록이라 미제공이다(점검이 있다고도 없다고도 추정하지 않는다).
 * 승인 차단은 서버 판정(PlanSupport.implementation_allowed)을 따르고, 여기서는 표시만 한다.
 */
export function acCoverage(plan: PlanView): AcCoverage {
  if (plan.verification === undefined && plan.manual_acceptance === undefined) return { kind: 'missing' }
  const checks = plan.verification ?? []
  const manual = plan.manual_acceptance ?? []
  const rows = plan.acceptance.map((ac): AcRow => {
    const linked = checks.filter((c) => c.ac_ids.includes(ac.id))
    const human = manual.find((m) => m.ac_id === ac.id) ?? null
    return { ac, checks: linked, manual: human, uncovered: linked.length === 0 && human === null }
  })
  return { kind: 'known', rows, uncoveredCount: rows.filter((r) => r.uncovered).length }
}

export const WORK_KIND_NAME: Record<WorkItem['kind'], string> = {
  contract: '계약',
  infra: '인프라',
  backend: '백엔드',
  frontend: '프런트엔드',
  ai_data: 'AI·데이터',
  integration: '통합',
}

/** 점검 한 건을 한 줄로: 무엇을 하고 무엇을 기대하는지 */
export function describeCheck(c: CheckSpec): { kind: string; text: string } {
  switch (c.kind) {
    case 'http':
      return { kind: 'HTTP 점검', text: c.steps.map((s) => `${s.method} ${s.path} → 상태 ${s.expect.status}`).join(' · ') }
    case 'command': {
      const out = c.expect.stdout_contains?.length ? ` · 출력에 ${c.expect.stdout_contains.map((x) => `“${x}”`).join(', ')}` : ''
      return { kind: '명령 점검', text: `${c.argv.join(' ')} → 종료 코드 ${c.expect.exit}${out}` }
    }
    case 'file': {
      const has = c.expect.contains?.length ? ` · 내용에 ${c.expect.contains.map((x) => `“${x}”`).join(', ')}` : ''
      return { kind: '파일 점검', text: `${c.path} ${c.expect.exists ? '있음' : '없음'}${has}` }
    }
  }
}
