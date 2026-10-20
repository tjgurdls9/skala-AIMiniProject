<script setup lang="ts">
import { computed, ref } from 'vue'
import type { RunEvent, Task, WorkKind } from '../api/types'
import { EVENT_TYPE, formatClock, formatTime, WORK_KIND } from '../model/labels'
import { eventEmphasis, groupRepeats, keepWhenFiltered, relatedTaskIds } from '../model/relevance'

/** 시간순 사건 기록. 관심 분야는 강조만 하고 순서를 바꾸지 않는다(로컬 관련도 보조). */
const props = defineProps<{ events: RunEvent[]; tasks: Task[] }>()
const emit = defineEmits<{ task: [id: string] }>()

const PAGE = 60
const INTERESTS: WorkKind[] = ['frontend', 'backend', 'infra', 'ai_data', 'security', 'release']

const interests = ref<Set<WorkKind>>(new Set())
const onlyRelated = ref(false)
const limit = ref(PAGE)

const related = computed(() => relatedTaskIds(props.tasks, interests.value))
const filtered = computed(() => {
  const all = groupRepeats(props.events)
  return onlyRelated.value && interests.value.size ? all.filter((g) => keepWhenFiltered(g.last, related.value)) : all
})
const groups = computed(() => filtered.value.slice(-limit.value))
const hidden = computed(() => Math.max(0, filtered.value.length - limit.value))

function toggle(kind: WorkKind): void {
  const next = new Set(interests.value)
  if (next.has(kind)) next.delete(kind)
  else next.add(kind)
  interests.value = next
}
</script>

<template>
  <section class="log panel" aria-labelledby="log-title">
    <header>
      <h2 id="log-title">사건 기록</h2>
      <span class="small muted">{{ events.length }}건 · 오래된 순</span>
    </header>
    <fieldset class="interests">
      <legend class="small">관심 분야 강조 <span class="chip">로컬 관련도 보조 · 작업 분야·의존 관계 기반</span></legend>
      <button
        v-for="k in INTERESTS"
        :key="k"
        type="button"
        class="btn small"
        :aria-pressed="interests.has(k)"
        @click="toggle(k)"
      >{{ WORK_KIND[k] }}</button>
      <label class="small only">
        <input v-model="onlyRelated" type="checkbox" :disabled="!interests.size" />
        강조 항목만 (승인·대기·경고·작업 종료·검토·상태 변경은 항상 표시)
      </label>
    </fieldset>
    <button v-if="hidden" type="button" class="btn small more" @click="limit += PAGE">이전 사건 {{ hidden }}건 더 보기</button>
    <ol class="plain entries">
      <li v-for="g in groups" :key="g.key" :class="['entry', eventEmphasis(g.last, related)]">
        <time class="time small muted" :datetime="g.last.occurred_at" :title="formatTime(g.last.occurred_at)">{{ formatClock(g.last.occurred_at) }}</time>
        <span class="type small">
          <span v-if="eventEmphasis(g.last, related) === 'critical'" aria-label="주의">⚑</span>
          <span v-else-if="eventEmphasis(g.last, related) === 'related'" aria-label="관심 분야">★</span>
          {{ EVENT_TYPE[g.last.event_type] }}<template v-if="g.count > 1"> ×{{ g.count }}</template>
        </span>
        <span class="summary">
          <template v-if="g.count > 1">{{ g.first.summary }} … </template>{{ g.last.summary }}
          <button v-if="g.last.task_id" type="button" class="task-link small" @click="emit('task', g.last.task_id!)">작업 보기</button>
        </span>
      </li>
      <li v-if="!groups.length" class="muted">아직 사건이 없습니다.</li>
    </ol>
  </section>
</template>

<style scoped>
.log { display: grid; gap: 8px; }
.interests { border: 0; padding: 0; margin: 0; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.interests legend { width: 100%; margin-bottom: 4px; }
.interests .btn[aria-pressed="true"] { background: var(--ink); color: var(--bg); }
.only { display: inline-flex; gap: 6px; align-items: center; min-height: var(--tap); }
.entries { max-height: 320px; overflow: auto; }
.entry { display: grid; grid-template-columns: 76px 140px 1fr; gap: 4px 10px; padding: 6px 4px; border-bottom: 1px solid var(--line); }
.entry.critical { border-left: 3px solid var(--tone-warn); padding-left: 8px; }
.entry.related { background: var(--surface-2); }
.task-link { margin-left: 6px; border: 0; background: none; color: var(--focus); text-decoration: underline; cursor: pointer; min-height: 32px; }
.more { justify-self: start; }
@media (max-width: 760px) { .entry { grid-template-columns: 1fr; } }
</style>
