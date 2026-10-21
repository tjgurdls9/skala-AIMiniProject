import { computed, ref, shallowRef, watch, type Ref } from 'vue'
import { ApiError } from '../api/errors'
import type { RunSource } from '../api/source'
import type { RunEvent, Snapshot } from '../api/types'

/** 출시 원장이 바뀌었을 수 있는 사건. 같은 state_version에서도 올 수 있다 */
const RELEASE_EVENTS = new Set<RunEvent['event_type']>([
  'approval_requested', 'approval_decided', 'approval_invalidated', 'deployment_started', 'deployment_finished', 'operation_uncertain',
])

/**
 * CR-C15 출시·복구 보기를 읽는다. 상태 버전이 바뀌거나 출시 관련 사건이 오면 다시 읽고, 늦게 온 옛 응답은 버린다.
 * 조회 실패 시 이전 보기를 지운다(옛 결과를 현재로 보이지 않게).
 */
export function useRelease(source: RunSource, snapshot: Ref<Snapshot | null>, events: Ref<readonly RunEvent[]>) {
  const view = shallowRef<unknown>(null)
  const error = ref<string | null>(null)
  let token = 0

  async function refresh(): Promise<void> {
    const mine = ++token
    try {
      const next = await source.getRelease()
      if (mine !== token) return
      view.value = next
      error.value = null
    } catch (e) {
      if (mine !== token) return
      view.value = null
      error.value = e instanceof ApiError ? e.message : '서버 응답을 확인하세요.'
    }
  }

  const key = computed(() => `${snapshot.value?.state_version ?? -1}:${events.value.filter((e) => RELEASE_EVENTS.has(e.event_type)).length}`)
  watch(key, () => {
    if (snapshot.value) void refresh()
  }, { immediate: true })

  return { view, error, refresh }
}
