import type { ContextEvidence, RetrievalEvidence } from '../api/types'

const DIGEST = /^sha256:[a-f0-9]{64}$/
const ROLES = new Set(['planner', 'builder', 'validator', 'security'])
const ERROR_CODES = new Set(['MODEL_UNAVAILABLE', 'VERSION_CONFLICT', 'INVALID_SOURCE', 'SEARCH_FAILED'])
const RETRIEVAL_KEYS = new Set(['role', 'method', 'status', 'model', 'error_code', 'sources'])
const RETRIEVAL_SOURCE_KEYS = new Set(['chunk_id', 'url', 'version', 'license', 'collected_at', 'content_digest', 'roles', 'score'])
const CONTEXT_KEYS = new Set(['spec_version_id', 'status', 'source_digest', 'completed_fragments', 'total_fragments', 'sources'])
const CONTEXT_SOURCE_KEYS = new Set(['request_id', 'content_digest', 'offset', 'length'])

const isDigest = (v: unknown): v is string => typeof v === 'string' && DIGEST.test(v)
const isText = (v: unknown): v is string => typeof v === 'string' && v.length > 0
const isCount = (v: unknown, min = 0): boolean => Number.isInteger(v) && (v as number) >= min
const isRecord = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v)
/** 스키마의 additionalProperties: false */
const onlyKeys = (v: Record<string, unknown>, keys: ReadonlySet<string>): boolean => Object.keys(v).every((k) => keys.has(k))
const isRoleSet = (v: unknown): boolean =>
  Array.isArray(v) && v.length > 0 && new Set(v).size === v.length && v.every((r) => ROLES.has(r as string))

function isRetrievalSource(s: unknown): boolean {
  return isRecord(s) && onlyKeys(s, RETRIEVAL_SOURCE_KEYS)
    && isDigest(s.chunk_id) && typeof s.url === 'string' && isText(s.version) && isText(s.license)
    && typeof s.collected_at === 'string' && isDigest(s.content_digest) && isRoleSet(s.roles) && typeof s.score === 'number'
}

/** http.RetrievalEvidence 형태인지 확인한다(서버·가져온 기록의 본문을 그대로 신뢰하지 않음). 화면이 조회하는 열거 값은 원소까지 확인한다 */
export function isRetrievalEvidence(value: unknown): value is RetrievalEvidence {
  if (!isRecord(value) || !onlyKeys(value, RETRIEVAL_KEYS)) return false
  const v = value
  if (!ROLES.has(v.role as string) || !['keyword', 'semantic'].includes(v.method as string)) return false
  if (!['found', 'no_results', 'search_error'].includes(v.status as string)) return false
  if (v.model !== null && typeof v.model !== 'string') return false
  if ('error_code' in v && !ERROR_CODES.has(v.error_code as string)) return false
  return Array.isArray(v.sources) && v.sources.length <= 5 && v.sources.every(isRetrievalSource)
}

function isContextSource(s: unknown): boolean {
  return isRecord(s) && onlyKeys(s, CONTEXT_SOURCE_KEYS)
    && isText(s.request_id) && isDigest(s.content_digest) && isCount(s.offset) && isCount(s.length, 1)
}

/** http.ContextEvidence 형태인지 확인한다 */
export function isContextEvidence(value: unknown): value is ContextEvidence {
  if (!isRecord(value) || !onlyKeys(value, CONTEXT_KEYS)) return false
  const v = value
  if (!['ready', 'needs_input'].includes(v.status as string) || !isDigest(v.source_digest)) return false
  if (!isCount(v.completed_fragments) || !isCount(v.total_fragments)) return false
  if (v.spec_version_id !== null && !isText(v.spec_version_id)) return false
  return Array.isArray(v.sources) && v.sources.every(isContextSource)
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
