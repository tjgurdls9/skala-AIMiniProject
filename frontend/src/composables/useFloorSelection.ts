import { ref, watch, type Ref } from 'vue'

/**
 * 어느 층(Sprint)을 보고 있는지. 현재 Sprint는 스냅샷에서 도출한 값만 따른다(추측하지 않는다).
 * - 직접 고른 적이 없으면 현재 Sprint가 바뀔 때 자동으로 따라간다.
 * - 직접 고른 뒤에는 따라가지 않고 "현재 Sprint가 바뀜" 알림만 남긴다.
 */
interface Options {
  currentId: Ref<string | null>
  /** 현재 Sprint를 아직 도출하지 못했을 때 쓸 첫 층 */
  firstId: Ref<string | null>
}

export function useFloorSelection(options: Options) {
  const selectedId = ref<string | null>(options.currentId.value ?? options.firstId.value)
  const userPicked = ref(false)
  /** 직접 고른 뒤 현재 Sprint가 이 층으로 바뀌었다는 알림(없으면 null) */
  const notice = ref<string | null>(null)

  watch(options.currentId, (id) => {
    if (!id) return
    if (!userPicked.value) {
      selectedId.value = id
      return
    }
    notice.value = id === selectedId.value ? null : id
  })
  // 첫 층·현재 층이 늦게 생기는 경우(스냅샷 도착 전)
  watch(options.firstId, (id) => {
    if (selectedId.value === null) selectedId.value = options.currentId.value ?? id
  })
  watch(options.currentId, (id) => {
    if (selectedId.value === null && id) selectedId.value = id
  })

  function pick(id: string): void {
    userPicked.value = true
    selectedId.value = id
    if (notice.value === id) notice.value = null
  }
  function dismiss(): void {
    notice.value = null
  }

  return { selectedId, notice, pick, dismiss }
}
