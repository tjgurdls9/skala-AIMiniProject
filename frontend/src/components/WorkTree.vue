<script setup lang="ts">
import { computed } from 'vue'
import type { Snapshot } from '../api/types'
import { orderedPhases, sprintsOf, tallySprint, tasksOf } from '../model/derive'
import { shortId, TASK_STATE } from '../model/labels'

/** 프로젝트 → Phase → Sprint → 작업 → 아티팩트 탐색. 선택은 부모의 view state이며 서버 상태가 아니다. */
const props = defineProps<{
  snapshot: Snapshot
  sprintId: string | null
  taskId: string | null
  artifactId: string | null
  currentSprintId: string | null
}>()
const emit = defineEmits<{ sprint: [id: string]; task: [id: string]; artifact: [id: string] }>()

const artifactsById = computed(() => new Map(props.snapshot.artifacts.map((a) => [a.id, a])))
const phases = computed(() =>
  orderedPhases(props.snapshot).map((phase) => ({
    phase,
    sprints: sprintsOf(props.snapshot, phase.id).map((sprint) => ({ sprint, tally: tallySprint(props.snapshot, sprint), tasks: tasksOf(props.snapshot, sprint.id) })),
  })),
)
</script>

<template>
  <nav class="tree panel" aria-label="작업 지도">
    <header><h2>작업 지도</h2><span class="small muted">{{ snapshot.tasks.length }}개 작업</span></header>
    <p class="small muted project">프로젝트 <code :title="snapshot.project_id">{{ shortId(snapshot.project_id) }}</code></p>
    <ol class="plain phases">
      <li v-for="{ phase, sprints } in phases" :key="phase.id">
        <h3 class="phase">{{ phase.order + 1 }}. {{ phase.title }}</h3>
        <ol class="plain">
          <li v-for="{ sprint, tally, tasks } in sprints" :key="sprint.id">
            <button
              type="button"
              class="node sprint"
              :aria-current="sprint.id === sprintId ? 'true' : undefined"
              :aria-expanded="sprint.id === sprintId"
              @click="emit('sprint', sprint.id)"
            >
              <span>{{ sprint.title }}</span>
              <span class="small muted">
                완료 {{ tally.succeeded }}/{{ tally.total }}
                <template v-if="tally.failed + tally.blocked"> · <span class="tone-danger">문제 {{ tally.failed + tally.blocked }}</span></template>
                <template v-if="sprint.id === currentSprintId"> · 현재(도출)</template>
              </span>
            </button>
            <ol v-if="sprint.id === sprintId" class="plain tasks">
              <li v-for="t in tasks" :key="t.id">
                <button
                  type="button"
                  class="node task"
                  :aria-current="t.id === taskId ? 'true' : undefined"
                  @click="emit('task', t.id)"
                >
                  <span :class="['tone', `tone-${TASK_STATE[t.state].tone}`]" :title="TASK_STATE[t.state].text">
                    {{ TASK_STATE[t.state].glyph }}<span class="sr-only">{{ TASK_STATE[t.state].text }}</span>
                  </span>
                  <span>{{ t.title }}</span>
                </button>
                <ul v-if="t.id === taskId && t.artifact_ids.length" class="plain artifacts">
                  <li v-for="aid in t.artifact_ids" :key="aid">
                    <button
                      type="button"
                      class="node artifact"
                      :aria-current="aid === artifactId ? 'true' : undefined"
                      :disabled="!artifactsById.has(aid)"
                      @click="emit('artifact', aid)"
                    >
                      ▤ {{ artifactsById.get(aid)?.title ?? `${aid} (아직 없음)` }}
                    </button>
                  </li>
                </ul>
              </li>
            </ol>
          </li>
        </ol>
      </li>
    </ol>
  </nav>
</template>

<style scoped>
.tree { overflow: auto; }
.project { margin-bottom: 8px; }
.phase { font-size: 0.8rem; color: var(--ink-3); text-transform: none; margin: 10px 0 4px; }
.node {
  width: 100%; min-height: 40px; display: flex; gap: 8px; align-items: center; justify-content: space-between; flex-wrap: wrap;
  padding: 6px 8px; border: 0; border-radius: 6px; background: none; text-align: left; cursor: pointer;
}
.node:hover:not(:disabled) { background: var(--surface-2); }
.node[aria-current="true"] { background: var(--surface-2); box-shadow: inset 3px 0 0 var(--focus); font-weight: 600; }
.node:disabled { color: var(--ink-3); cursor: default; }
.tasks { padding-left: 12px; border-left: 1px dashed var(--line); margin-left: 8px; }
.task { justify-content: flex-start; flex-wrap: nowrap; font-size: 0.92rem; }
.artifacts { padding-left: 20px; }
.artifact { min-height: 36px; font-size: 0.85rem; }
</style>
