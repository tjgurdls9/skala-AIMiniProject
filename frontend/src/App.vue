<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { LiveApi, liveSource } from './api/live'
import type { RunSource } from './api/source'
import { exampleSource } from './examples/exampleSource'
import { findScenario } from './examples/scenarios'
import type { Origin } from './model/prompt'
import RunWorkspace from './components/RunWorkspace.vue'
import StartScreen from './components/StartScreen.vue'

/** 화면 위치는 URL 쿼리(?run= / ?example=)로 유지해 새로고침해도 같은 실행으로 돌아온다. */
const api = new LiveApi()
const params = ref(new URLSearchParams(window.location.search))
const REVEAL_MS = 520

const source = computed<RunSource | null>(() => {
  const runId = params.value.get('run')
  if (runId) return liveSource(api, runId)
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

type ViewTransitionDoc = Document & { startViewTransition?: (cb: () => Promise<void>) => { ready: Promise<void> } }

/**
 * 입력 위치에서 원이 퍼지며 사무실이 화면을 채운다(View Transitions API, MDN의 원형 공개 패턴).
 * 지원하지 않거나 모션 감소 설정이면 바로 바꾼다.
 */
function navigate(next: Record<string, string>, origin?: Origin): void {
  const doc = document as ViewTransitionDoc
  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  if (!origin || reduce || typeof doc.startViewTransition !== 'function') {
    apply(next)
    return
  }
  const transition = doc.startViewTransition(async () => {
    apply(next)
    await nextTick()
  })
  const radius = Math.hypot(Math.max(origin.x, window.innerWidth - origin.x), Math.max(origin.y, window.innerHeight - origin.y))
  void transition.ready.then(() => {
    document.documentElement.animate(
      { clipPath: [`circle(0px at ${origin.x}px ${origin.y}px)`, `circle(${radius}px at ${origin.x}px ${origin.y}px)`] },
      { duration: REVEAL_MS, easing: 'cubic-bezier(0.2, 0.8, 0.2, 1)', pseudoElement: '::view-transition-new(root)' },
    )
  })
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
/* 기본 교차 페이드 대신 위 원형 공개만 쓴다 */
::view-transition-old(root),
::view-transition-new(root) {
  animation: none;
  mix-blend-mode: normal;
}
</style>
