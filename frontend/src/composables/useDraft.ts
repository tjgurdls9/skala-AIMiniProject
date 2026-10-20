import { ref, watch, type Ref } from 'vue'

/** 피드백 초안을 탭 세션에 보존한다(재접속·새로고침·409에도 유지). 저장소가 막혀도 메모리로 동작한다. */
export function useDraft(key: string): { text: Ref<string>; clear: () => void } {
  const read = (): string => {
    try {
      return sessionStorage.getItem(key) ?? ''
    } catch {
      return ''
    }
  }
  const text = ref(read())
  watch(text, (value) => {
    try {
      if (value) sessionStorage.setItem(key, value)
      else sessionStorage.removeItem(key)
    } catch {
      // 저장 불가: 메모리 값만 유지
    }
  })
  return { text, clear: () => (text.value = '') }
}
