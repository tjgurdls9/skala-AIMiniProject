<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { RunEvent, Snapshot } from '../api/types'
import { formatIdle, idleSeconds, modelWork } from '../model/modelWork'

/**
 * 모델 작업 단계에서 사건이 없을 때 화면이 멈춘 것처럼 보이지 않게 하는 겹침 표시.
 * 서버 상태와 사건에서만 도출하며 진행률·남은 시간은 알 수 없어 쓰지 않는다.
 * 클릭을 가로채지 않는다. 보이는 표시는 스크린리더에서 숨기고 단계가 바뀔 때만 polite로 알린다.
 */
const props = defineProps<{ snapshot: Snapshot; lastEvent: RunEvent | null; receivedAt: number; animated: boolean }>()

const TICK_MS = 1000
const MAX_RUNNING_SHOWN = 2

const now = ref(Date.now())
let timer: ReturnType<typeof setInterval> | null = null
onMounted(() => {
  timer = setInterval(() => (now.value = Date.now()), TICK_MS)
})
onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})

const work = computed(() => modelWork(props.snapshot))
const announce = computed(() => (work.value ? `${work.value.stage} · 로컬 모델 응답 대기` : ''))
const idle = computed(() => formatIdle(idleSeconds(props.lastEvent?.occurred_at, props.receivedAt, now.value)))
const running = computed(() => {
  const titles = work.value?.running ?? []
  const shown = titles.slice(0, MAX_RUNNING_SHOWN).join(', ')
  return titles.length > MAX_RUNNING_SHOWN ? `${shown} 외 ${titles.length - MAX_RUNNING_SHOWN}건` : shown
})
</script>

<template>
  <div class="model-work">
    <p class="sr-only" role="status" aria-live="polite">{{ announce }}</p>
    <div v-if="work" class="work-pill" aria-hidden="true">
      <span :class="['spin', { animated }]" />
      <div class="body">
        <strong>{{ announce }}</strong>
        <span v-if="running" class="small">진행 중 작업: {{ running }}</span>
        <span v-if="lastEvent" class="small">마지막 사건: {{ lastEvent.summary }}</span>
        <span class="small muted">마지막 진행 {{ idle }} 전 · 진행률은 알 수 없습니다</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.work-pill {
  position: fixed; top: calc(var(--header-h, 64px) + 10px); left: 50%; transform: translateX(-50%); z-index: 35;
  display: flex; gap: 10px; align-items: center; max-width: min(520px, 90vw); padding: 8px 14px;
  border: 1px solid var(--line); border-radius: 999px; background: var(--surface); color: var(--ink);
  box-shadow: 0 6px 22px rgb(0 0 0 / 14%); pointer-events: none;
}
.body { display: grid; gap: 1px; min-width: 0; }
.body span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.spin { flex: none; width: 18px; height: 18px; border-radius: 50%; border: 3px solid var(--line); border-top-color: var(--live, currentColor); }
.spin.animated { animation: work-spin 0.9s linear infinite; }
@keyframes work-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .spin.animated { animation: none; } }
</style>
