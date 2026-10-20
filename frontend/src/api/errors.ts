import type { ApiErrorBody } from './types'

export type ApiErrorCode = ApiErrorBody['error']['code'] | 'NETWORK' | 'BAD_RESPONSE' | 'EXAMPLE_NOOP'

/** 서버 오류 본문(http.Error) 또는 전송 실패를 하나로 다룬다. message는 화면 표시용이다. */
export class ApiError extends Error {
  readonly status: number
  readonly code: ApiErrorCode
  readonly currentStateVersion?: number

  constructor(status: number, code: ApiErrorCode, message: string, currentStateVersion?: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.currentStateVersion = currentStateVersion
  }

  /** 최신 대상을 다시 읽어야 하는 충돌(409)인가 */
  get isStale(): boolean {
    return this.code === 'VERSION_CONFLICT' || this.code === 'STALE_APPROVAL' || this.code === 'INVALID_STATE'
  }
}

const KNOWN_CODES = new Set<string>([
  'UNAUTHORIZED', 'FORBIDDEN', 'NOT_FOUND', 'VERSION_CONFLICT', 'COMMAND_CONFLICT', 'STALE_APPROVAL',
  'INVALID_COMMAND', 'PROVIDER_NOT_FREE', 'RUNTIME_UNAVAILABLE', 'REPLAY_READ_ONLY',
  'TEMPORARILY_UNAVAILABLE', 'CURSOR_INVALID', 'INVALID_STATE', 'BODY_TOO_LARGE',
])

/** 응답 본문을 신뢰하지 않고 http.Error 형태일 때만 코드를 채택한다. */
export function toApiError(status: number, body: unknown): ApiError {
  const err = (body as { error?: { code?: unknown; message?: unknown; current_state_version?: unknown } } | null)?.error
  if (err && typeof err.code === 'string' && KNOWN_CODES.has(err.code)) {
    const message = typeof err.message === 'string' && err.message ? err.message : `요청 실패 (${status})`
    const version = typeof err.current_state_version === 'number' ? err.current_state_version : undefined
    return new ApiError(status, err.code as ApiErrorCode, message, version)
  }
  return new ApiError(status, 'BAD_RESPONSE', `서버 응답을 해석할 수 없습니다 (${status})`)
}

/** 사용자에게 보여줄 다음 행동 */
export function errorHint(error: ApiError): string {
  switch (error.code) {
    case 'VERSION_CONFLICT':
    case 'STALE_APPROVAL':
    case 'INVALID_STATE':
      return '대상이 바뀌었습니다. 최신 상태를 다시 불러왔으니 내용을 확인한 뒤 다시 결정하세요. 입력한 의견은 보존됩니다.'
    case 'COMMAND_CONFLICT':
      return '같은 명령 ID로 다른 내용이 접수돼 있습니다. 새 명령으로 다시 보내세요.'
    case 'REPLAY_READ_ONLY':
      return '실제 기록 재생은 읽기 전용입니다. 새 LIVE 실행을 만들어야 명령을 보낼 수 있습니다.'
    case 'RUNTIME_UNAVAILABLE':
    case 'PROVIDER_NOT_FREE':
      return '실행 환경이 준비되지 않았습니다. 실행 가능성 표시를 확인하거나 실제 기록 재생을 선택하세요.'
    case 'UNAUTHORIZED':
    case 'FORBIDDEN':
      return '로컬 세션이 만료됐습니다. 다시 연결하세요.'
    case 'NETWORK':
      return '서버에 연결하지 못했습니다. 실행 상태가 바뀐 것은 아닙니다.'
    case 'EXAMPLE_NOOP':
      return '합성 예시에서는 명령을 보내지 않습니다. 외부 승인·배포도 실행되지 않습니다.'
    default:
      return '잠시 후 다시 시도하세요.'
  }
}
