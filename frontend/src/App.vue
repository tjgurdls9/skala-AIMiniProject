<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { LiveApi, liveSource } from './api/live'
import type { RunSource } from './api/source'
import { exampleSource } from './examples/exampleSource'
import { FULL_CYCLE_ID, fullCycleSource } from './examples/fullCycle'
import { findScenario } from './examples/scenarios'
import type { Origin } from './model/prompt'
import RunWorkspace from './components/RunWorkspace.vue'
import StartScreen from './components/StartScreen.vue'

/** 화면 위치는 URL 쿼리(?run= / ?example=)로 유지해 새로고침해도 같은 실행으로 돌아온다. */
const api = new LiveApi()
const params = ref(new URLSearchParams(window.location.search))

const source = computed<RunSource | null>(() => {
  const runId = params.value.get('run')
  if (runId) return liveSource(api, runId)
  if (params.value.get('example') === FULL_CYCLE_ID) return fullCycleSource()
  const scenario = findScenario(params.value.get('example'))
  return scenario ? exampleSource(scenario) : null
})
const sourceKey = computed(() => `${params.value.get('run') ?? ''}|${params.value.get('example') ?? ''}`)

function apply(next: Record<string, string>): void {
  const search = new URLSearchParams(next)
  const query = search.toString()
  window.history.pushState(null, '', query ? `?${query}` : window.location.pathname)
  params.value = search
  window.scrollTo(0, 0)
}

const WARP_IN_MS = 560
const WARP_OUT_MS = 520

/**
 * 극적인 전환: 입력 위치에서 빛나는 고리를 두른 어둠이 화면을 삼키고(이전 화면은 뒤로 물러나며 흐려짐),
 * 그 아래에서 사무실이 열린 뒤 어둠이 걷힌다.
 * 모션 감소이거나 Web Animations를 쓸 수 없으면 바로 바꾼다.
 */
async function navigate(next: Record<string, string>, origin?: Origin): Promise<void> {
  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  if (!origin || reduce || typeof document.body.animate !== 'function') {
    apply(next)
    return
  }
  const cover = Math.hypot(Math.max(origin.x, window.innerWidth - origin.x), Math.max(origin.y, window.innerHeight - origin.y)) * 2.3
  const warp = document.createElement('div')
  warp.className = 'warp'
  warp.setAttribute('aria-hidden', 'true')
  warp.style.left = `${origin.x}px`
  warp.style.top = `${origin.y}px`
  warp.style.width = warp.style.height = `${cover}px`
  document.body.append(warp)
  document.documentElement.classList.add('warping')
  try {
    await warp.animate(
      [{ transform: 'translate(-50%, -50%) scale(0.001)' }, { transform: 'translate(-50%, -50%) scale(1)' }],
      { duration: WARP_IN_MS, easing: 'cubic-bezier(0.7, 0, 0.84, 0)', fill: 'forwards' },
    ).finished
    apply(next)
    await nextTick()
  } finally {
    document.documentElement.classList.remove('warping')
  }
  await warp.animate([{ opacity: 1 }, { opacity: 0 }], { duration: WARP_OUT_MS, easing: 'ease-out', fill: 'forwards' }).finished
  warp.remove()
}

const onPop = () => {
  params.value = new URLSearchParams(window.location.search)
}
onMounted(() => window.addEventListener('popstate', onPop))
onBeforeUnmount(() => window.removeEventListener('popstate', onPop))
</script>

<template>
  <RunWorkspace v-if="source" :key="sourceKey" :source="source" @home="navigate({})" />
  <StartScreen
    v-else
    :api="api"
    @open-run="(id, origin) => navigate({ run: id }, origin)"
    @open-example="(id, origin) => navigate({ example: id }, origin)"
  />
</template>

<style>
/* 전환 중 이전 화면은 뒤로 물러나며 흐려진다 */
html.warping #app > * {
  transition: transform 0.56s cubic-bezier(0.7, 0, 0.84, 0), filter 0.56s ease-in;
  transform: scale(0.93);
  filter: blur(6px) brightness(0.7);
}
/* 빛나는 고리를 두른 어둠(가장자리에 따뜻한 빛, 바깥은 투명) */
.warp {
  position: fixed;
  z-index: 1000;
  border-radius: 50%;
  pointer-events: none;
  transform: translate(-50%, -50%) scale(0.001);
  background: #0d1013;
  /* 가장자리 빛 고리: 단색 테두리 두 겹 */
  box-shadow: 0 0 0 6px #ffd27a, 0 0 0 14px rgb(255 210 122 / 0.25);
}
</style>
