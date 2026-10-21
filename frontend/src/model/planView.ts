import type { PlanView } from '../api/types'
import { isPlanSupport } from './planSupport'

/** 계약 enum(fa07aec): 기존 문구(과거 기록)와 외부 모델 금지·무료 데이터 조건 문구. 그 밖의 정책은 받지 않는다. */
const FREE_POLICIES = {
  'Local Ollama Qwen/DeepSeek only; no paid fallback or external API.': true,
  'Inference: local Ollama Qwen/DeepSeek only; no paid fallback or external model API. External data: verified free terms, explicit consent, fixed isolated access, no paid overage.': true,
} satisfies Record<PlanView['free_policy'], true>
const isFreePolicy = (v: unknown): boolean => typeof v === 'string' && Object.hasOwn(FREE_POLICIES, v)

const isStrings = (v: unknown): v is string[] => Array.isArray(v) && v.every((x) => typeof x === 'string')

/** 서버 응답을 신뢰하지 않고 PlanView의 필수 필드를 모두 확인한다. 하나라도 어긋나면 승인 화면에 쓰지 않는다. */
export function isPlanView(value: unknown): value is PlanView {
  const v = value as Partial<PlanView> | null
  if (!v || typeof v !== 'object') return false
  if (typeof v.goal !== 'string' || typeof v.spec_version_id !== 'string' || !isFreePolicy(v.free_policy)) return false
  if (![v.features, v.non_goals, v.constraints, v.assumptions, v.changes, v.stack, v.allowed_tools].every(isStrings)) return false
  if (!Array.isArray(v.acceptance) || !v.acceptance.every((a) => a && typeof a.id === 'string' && typeof a.title === 'string' && typeof a.description === 'string')) return false
  if (v.repository !== null && (typeof v.repository !== 'object' || typeof v.repository?.url !== 'string' || typeof v.repository?.branch !== 'string')) return false
  if (v.deployment !== null && (typeof v.deployment !== 'object' || typeof v.deployment?.label !== 'string')) return false
  // CR-C14 support는 선택 필드다. 있으면 계약 형식이어야 한다(없으면 지원 정보 미제공으로 따로 표시)
  if (v.support !== undefined && !isPlanSupport(v.support)) return false
  return !!v.contract_digests && typeof v.contract_digests === 'object'
}
