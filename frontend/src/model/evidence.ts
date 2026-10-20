import type { ContextEvidence, RetrievalEvidence } from '../api/types'

const DIGEST = /^sha256:[a-f0-9]{64}$/
const ROLES = new Set(['planner', 'builder', 'validator', 'security'])
const isDigest = (v: unknown): v is string => typeof v === 'string' && DIGEST.test(v)

/** http.RetrievalEvidence 형태인지 확인한다(서버 응답을 그대로 신뢰하지 않음) */
export function isRetrievalEvidence(value: unknown): value is RetrievalEvidence {
  const v = value as Partial<RetrievalEvidence> | null
  if (!v || typeof v !== 'object') return false
  if (!ROLES.has(v.role as string) || !['keyword', 'semantic'].includes(v.method as string)) return false
  if (!['found', 'no_results', 'search_error'].includes(v.status as string)) return false
  if (v.model !== null && typeof v.model !== 'string') return false
  if (!Array.isArray(v.sources) || v.sources.length > 5) return false
  return v.sources.every((s) =>
    s && isDigest(s.chunk_id) && typeof s.url === 'string' && typeof s.version === 'string' && typeof s.license === 'string'
    && typeof s.collected_at === 'string' && isDigest(s.content_digest) && Array.isArray(s.roles) && typeof s.score === 'number')
}

/** http.ContextEvidence 형태인지 확인한다 */
export function isContextEvidence(value: unknown): value is ContextEvidence {
  const v = value as Partial<ContextEvidence> | null
  if (!v || typeof v !== 'object') return false
  if (!['ready', 'needs_input'].includes(v.status as string) || !isDigest(v.source_digest)) return false
  if (!Number.isInteger(v.completed_fragments) || !Number.isInteger(v.total_fragments)) return false
  if (v.spec_version_id !== null && typeof v.spec_version_id !== 'string') return false
  return Array.isArray(v.sources) && v.sources.every((s) =>
    s && typeof s.request_id === 'string' && isDigest(s.content_digest) && Number.isInteger(s.offset) && Number.isInteger(s.length))
}

/** 근거 출처 URL은 http(s)만 링크로 연다. 그 외는 텍스트로만 */
export function safeHttpUrl(url: string): string | null {
  try {
    const u = new URL(url)
    return u.protocol === 'http:' || u.protocol === 'https:' ? u.href : null
  } catch {
    return null
  }
}

export const RETRIEVAL_STATUS = {
  found: { text: '근거 찾음', glyph: '✓', tone: 'ok' },
  no_results: { text: '결과 없음', glyph: '○', tone: 'neutral' },
  search_error: { text: '검색 실패', glyph: '✕', tone: 'danger' },
} as const

export const RETRIEVAL_ERROR: Record<NonNullable<RetrievalEvidence['error_code']>, string> = {
  MODEL_UNAVAILABLE: '임베딩 모델을 쓸 수 없음',
  VERSION_CONFLICT: '문서 버전 충돌',
  INVALID_SOURCE: '허용되지 않은 출처',
  SEARCH_FAILED: '검색 실행 실패',
}
