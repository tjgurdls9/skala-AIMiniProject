<script setup lang="ts">
import { computed } from 'vue'
import type { PlanView } from '../api/types'
import { WORK_KIND_NAME } from '../model/planExtras'

/** CR-C17 작업 분해(종류·의존성·AC 연결·쓰기 범위)와 생략한 영역. 없으면 미제공이다. */
const props = defineProps<{ plan: PlanView }>()
const work = computed(() => props.plan.work_plan)
const omitted = computed(() => props.plan.omitted_areas ?? [])
</script>

<template>
  <section class="work" aria-label="작업 분해">
    <h3>작업 분해</h3>
    <p v-if="work === undefined" class="info-box small">미제공 · 미확인 — 서버가 이 기획의 작업 분해를 주지 않았습니다.</p>
    <p v-else-if="!work.length" class="small muted">분해된 작업이 없습니다.</p>
    <ol v-else class="plain items">
      <li v-for="w in work" :key="w.id" class="item small">
        <span class="line"><span class="chip">{{ WORK_KIND_NAME[w.kind] }}</span><strong>{{ w.title }}</strong> <code class="muted">{{ w.id }}</code></span>
        <span v-if="w.depends_on.length" class="muted">의존: {{ w.depends_on.join(', ') }}</span>
        <span class="muted">AC: {{ w.acceptance_ids.join(', ') }}</span>
        <span class="muted">쓰기 범위: <code v-for="s in w.write_scope" :key="s" class="scope">{{ s }}</code></span>
      </li>
    </ol>
    <template v-if="work !== undefined">
      <h4 class="small">생략한 영역</h4>
      <ul v-if="omitted.length" class="plain">
        <li v-for="o in omitted" :key="o.kind" class="small"><strong>{{ WORK_KIND_NAME[o.kind] }}</strong> — {{ o.reason }}</li>
      </ul>
      <p v-else class="small muted">생략한 영역 없음</p>
    </template>
  </section>
</template>

<style scoped>
.work { display: grid; gap: 6px; }
.work h4 { margin: 6px 0 2px; color: var(--ink-3); }
.items { display: grid; gap: 8px; }
.item { display: grid; gap: 2px; padding: 8px 10px; border: 1px solid var(--line); border-radius: var(--radius); background: var(--surface); }
.line { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 8px; }
.scope { margin-right: 6px; }
</style>
