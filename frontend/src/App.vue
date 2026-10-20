<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { LiveApi, liveSource } from './api/live'
import type { RunSource } from './api/source'
import { exampleSource } from './examples/exampleSource'
import { findScenario } from './examples/scenarios'
import RunWorkspace from './components/RunWorkspace.vue'
import StartScreen from './components/StartScreen.vue'

/** 화면 위치는 URL 쿼리(?run= / ?example=)로 유지해 새로고침해도 같은 실행으로 돌아온다. */
const api = new LiveApi()
const params = ref(new URLSearchParams(window.location.search))

const source = computed<RunSource | null>(() => {
  const runId = params.value.get('run')
  if (runId) return liveSource(api, runId)
  const scenario = findScenario(params.value.get('example'))
  return scenario ? exampleSource(scenario) : null
})
const sourceKey = computed(() => `${params.value.get('run') ?? ''}|${params.value.get('example') ?? ''}`)

function navigate(next: Record<string, string>): void {
  const search = new URLSearchParams(next)
  const query = search.toString()
  window.history.pushState(null, '', query ? `?${query}` : window.location.pathname)
  params.value = search
}
const onPop = () => {
  params.value = new URLSearchParams(window.location.search)
}
onMounted(() => window.addEventListener('popstate', onPop))
onBeforeUnmount(() => window.removeEventListener('popstate', onPop))
</script>

<template>
  <RunWorkspace v-if="source" :key="sourceKey" :source="source" @home="navigate({})" />
  <StartScreen v-else :api="api" @open-run="navigate({ run: $event })" @open-example="navigate({ example: $event })" />
</template>
