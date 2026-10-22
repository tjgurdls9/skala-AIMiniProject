<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { DemoControl as Demo } from '../api/source'

/** 합성 시연 전용 발표자 조작. 다음 단계 버튼 하나와 N 키. 사람 결정 대기 중에는 넘기지 않는다(승인은 대화상자에서) */
const props = defineProps<{ demo: Demo }>()

const info = ref(props.demo.info())
const stop = props.demo.onChange(() => {
  info.value = props.demo.info()
})
const status = computed(() => {
  if (info.value.waiting === 'plan') return '기획 승인 대기 — 대화상자에서 승인을 누르세요'
  if (info.value.waiting === 'acceptance') return '사람 확인 대기 — 대화상자에서 승인을 누르세요'
  return info.value.done ? '시연 끝 — 배포 승인 대상까지 진행했습니다' : info.value.label
})
const blocked = computed(() => info.value.waiting !== null || info.value.done)

function typing(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && (['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) || target.isContentEditable)
}
function onKey(e: KeyboardEvent): void {
  if (e.key.toLowerCase() !== 'n' || e.ctrlKey || e.metaKey || e.altKey || typing(e.target)) return
  props.demo.next()
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  stop()
})
</script>

<template>
  <aside class="demo-control" aria-label="합성 시연 조작">
    <p class="line"><strong>합성 시연</strong> <span class="muted small">{{ Math.max(info.index + 1, 0) }}/{{ info.total }}</span></p>
    <p class="status small" role="status">{{ status }}</p>
    <button type="button" class="btn small primary" :disabled="blocked" @click="demo.next()">다음 단계 → <kbd>N</kbd></button>
  </aside>
</template>

<style scoped>
.demo-control {
  position: fixed; left: 16px; bottom: 16px; z-index: 40; display: grid; gap: 4px; max-width: 260px;
  padding: 10px 12px; border-radius: var(--radius); border: 1px solid var(--example); background: var(--example-bg); color: var(--ink);
  box-shadow: 0 6px 22px rgb(0 0 0 / 18%);
}
.line { display: flex; gap: 8px; align-items: baseline; }
.status { color: var(--ink-2); }
kbd { margin-left: 4px; padding: 0 5px; border: 1px solid currentColor; border-radius: 4px; font: inherit; font-size: 0.75em; }
</style>
