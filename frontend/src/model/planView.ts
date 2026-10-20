import type { PlanView } from '../api/types'

const isStrings = (v: unknown): v is string[] => Array.isArray(v) && v.every((x) => typeof x === 'string')

/** 서버 응답을 신뢰하지 않고 PlanView의 필수 필드를 모두 확인한다. 하나라도 어긋나면 승인 화면에 쓰지 않는다. */
export function isPlanView(value: unknown): value is PlanView {
  const v = value as Partial<PlanView> | null
  if (!v || typeof v !== 'object') return false
  if (typeof v.goal !== 'string' || typeof v.spec_version_id !== 'string' || typeof v.free_policy !== 'string') return false
  if (![v.features, v.non_goals, v.constraints, v.assumptions, v.changes, v.stack, v.allowed_tools].every(isStrings)) return false
  if (!Array.isArray(v.acceptance) || !v.acceptance.every((a) => a && typeof a.id === 'string' && typeof a.title === 'string' && typeof a.description === 'string')) return false
  if (v.repository !== null && (typeof v.repository !== 'object' || typeof v.repository?.url !== 'string' || typeof v.repository?.branch !== 'string')) return false
  if (v.deployment !== null && (typeof v.deployment !== 'object' || typeof v.deployment?.label !== 'string')) return false
  return !!v.contract_digests && typeof v.contract_digests === 'object'
}
