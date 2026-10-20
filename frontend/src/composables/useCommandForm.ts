import { ref } from 'vue'
import { ApiError } from '../api/errors'
import { newCommandId } from './useRun'

export type SendResult = ApiError | null

/**
 * 한 번의 사용자 결정 = 한 명령 ID. 네트워크 오류 재시도는 같은 ID(중복 부작용 방지),
 * 대상이 바뀐 409 뒤에는 새 ID로 다시 검토하게 한다. 보내는 중에는 중복 클릭을 막는다.
 */
export function useCommandForm() {
  const commandId = ref(newCommandId())
  const submitting = ref(false)
  const error = ref<ApiError | null>(null)

  async function run(send: (commandId: string) => Promise<SendResult>): Promise<boolean> {
    if (submitting.value) return false
    submitting.value = true
    error.value = null
    try {
      const result = await send(commandId.value)
      if (!result) {
        commandId.value = newCommandId()
        return true
      }
      error.value = result
      if (result.isStale || result.code === 'COMMAND_CONFLICT') commandId.value = newCommandId()
      return false
    } finally {
      submitting.value = false
    }
  }

  /**
   * 새 결정을 시작한다: 새 명령 ID를 만든다(같은 ID 재사용은 열린 화면 안의 네트워크 재시도뿐).
   * 대상만 바뀐 경우(409 뒤 최신 대상 재조회)에는 원인 안내를 남긴다.
   */
  function renew(options: { keepError?: boolean } = {}): void {
    if (!options.keepError) error.value = null
    commandId.value = newCommandId()
  }

  return { commandId, submitting, error, run, renew }
}
