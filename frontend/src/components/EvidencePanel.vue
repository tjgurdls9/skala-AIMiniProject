<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ApiError, errorHint } from '../api/errors'
import type { RunSource } from '../api/source'
import type { AcceptanceItem, RunEvent, Snapshot } from '../api/types'
import { indexById, reviewPair, waitingReason } from '../model/derive'
import { isPlanView } from '../model/planView'
import { EVENT_TYPE, formatTime, ROLE, shortDigest, TASK_STATE, WORK_KIND } from '../model/labels'
import AcceptanceList from './AcceptanceList.vue'
import PlanViewBody from './PlanViewBody.vue'
import ReviewPair from './ReviewPair.vue'
import ReviewRounds from './ReviewRounds.vue'

const props = defineProps<{
  snapshot: Snapshot
  events: RunEvent[]
  source: RunSource
  taskId: string | null
  artifactId: string | null
  acIndex: ReadonlyMap<string, AcceptanceItem>
}>()
const emit = defineEmits<{ task: [id: string]; artifact: [id: string] }>()

const tasksById = computed(() => indexById(props.snapshot.tasks))
const task = computed(() => (props.taskId ? tasksById.value.get(props.taskId) ?? null : null))
const artifact = computed(() => props.snapshot.artifacts.find((a) => a.id === props.artifactId) ?? null)
const pair = computed(() => reviewPair(props.snapshot))
const taskEvents = computed(() => (task.value ? props.events.filter((e) => e.task_id === task.value?.id).slice(-8).reverse() : []))
const EVIDENCE_KINDS = new Set(['retrieval', 'context'])
/** 작업에 연결된 공개 검색·문맥 근거. 없으면 없음으로 표시하고 검색 결과로 추정하지 않는다 */
const evidenceArtifacts = computed(() =>
  task.value ? props.snapshot.artifacts.filter((a) => task.value!.artifact_ids.includes(a.id) && EVIDENCE_KINDS.has(a.kind)) : [],
)
const retrievalEvents = computed(() => taskEvents.value.filter((e) => e.event_type === 'retrieval_finished'))
const dependents = computed(() => (task.value ? props.snapshot.tasks.filter((t) => t.depends_on.includes(task.value!.id)) : []))

const body = ref<unknown>(null)
const bodyError = ref<string | null>(null)
const loading = ref(false)

watch(
  () => props.artifactId,
  async (id) => {
    body.value = null
    bodyError.value = null
    if (!id) return
    loading.value = true
    try {
      const value = await props.source.getArtifact(id)
      if (props.artifactId === id) body.value = value
    } catch (error) {
      if (props.artifactId === id) bodyError.value = error instanceof ApiError ? `${error.message} ${error.code === 'NOT_FOUND' ? '' : errorHint(error)}` : '본문을 읽지 못했습니다.'
    } finally {
      if (props.artifactId === id) loading.value = false
    }
  },
  { immediate: true },
)
</script>

<template>
  <aside class="evidence panel" aria-labelledby="evidence-title">
    <header><h2 id="evidence-title">근거</h2></header>

    <section v-if="artifact" class="block" aria-label="선택한 아티팩트">
      <p class="small muted">아티팩트 · {{ artifact.kind }}</p>
      <h3>{{ artifact.title }}</h3>
      <p>{{ artifact.public_summary }}</p>
      <p class="small muted">내용 해시 <code>{{ shortDigest(artifact.content_digest) }}</code></p>
      <p v-if="loading" class="small muted">본문 읽는 중…</p>
      <p v-else-if="bodyError" class="small muted">{{ bodyError }}</p>
      <PlanViewBody v-else-if="isPlanView(body)" :plan="body" />
      <pre v-else-if="body !== null" class="raw">{{ JSON.stringify(body, null, 2) }}</pre>
    </section>

    <section v-if="task" class="block" aria-label="선택한 작업">
      <p class="small muted">작업 <code>{{ task.id }}</code></p>
      <h3>{{ task.title }}</h3>
      <p :class="['tone', `tone-${TASK_STATE[task.state].tone}`]">{{ TASK_STATE[task.state].glyph }} {{ TASK_STATE[task.state].text }}</p>
      <dl class="kv small">
        <dt>담당</dt><dd>{{ ROLE[task.role].text }} · {{ WORK_KIND[task.work_kind] }}</dd>
        <dt>명세</dt><dd><code>{{ task.spec_version_id }}</code></dd>
        <dt>인수 기준</dt>
        <dd><AcceptanceList :ids="task.acceptance_ids" :index="acIndex" :reports="snapshot.reports" @artifact="emit('artifact', $event)" /></dd>
        <template v-if="waitingReason(task, tasksById)">
          <dt>대기·차단 이유</dt><dd>{{ waitingReason(task, tasksById) }}</dd>
        </template>
        <dt>선행 작업</dt>
        <dd>
          <span v-if="!task.depends_on.length" class="muted">없음</span>
          <button v-for="d in task.depends_on" :key="d" type="button" class="link" @click="emit('task', d)">
            {{ TASK_STATE[tasksById.get(d)?.state ?? 'pending'].glyph }} {{ tasksById.get(d)?.title ?? d }}
          </button>
        </dd>
        <template v-if="dependents.length">
          <dt>후속 작업</dt>
          <dd><button v-for="t in dependents" :key="t.id" type="button" class="link" @click="emit('task', t.id)">{{ t.title }}</button></dd>
        </template>
      </dl>
      <h4>아티팩트</h4>
      <ul class="plain">
        <li v-for="aid in task.artifact_ids" :key="aid">
          <button type="button" class="link" :disabled="!snapshot.artifacts.some((a) => a.id === aid)" @click="emit('artifact', aid)">
            ▤ {{ snapshot.artifacts.find((a) => a.id === aid)?.title ?? `${aid} (아직 없음)` }}
          </button>
        </li>
        <li v-if="!task.artifact_ids.length" class="muted small">없음</li>
      </ul>
      <h4>검색·문맥 근거</h4>
      <ul class="plain">
        <li v-for="a in evidenceArtifacts" :key="a.id">
          <button type="button" class="link" @click="emit('artifact', a.id)">⌕ {{ a.title }} <span class="small muted">({{ a.kind === 'retrieval' ? '검색' : '문맥' }})</span></button>
        </li>
        <li v-if="!evidenceArtifacts.length" class="muted small">
          이 작업에 공개된 검색·문맥 근거가 없습니다<template v-if="retrievalEvents.length"> (검색 사건 {{ retrievalEvents.length }}건은 기록에 있음)</template>.
          출처·버전 없는 근거를 추정해 표시하지 않습니다.
        </li>
      </ul>
      <h4>최근 사건</h4>
      <ol class="plain small">
        <li v-for="e in taskEvents" :key="e.seq">
          <span class="muted">{{ formatTime(e.occurred_at) }}</span> · {{ EVENT_TYPE[e.event_type] }} — {{ e.summary }}
        </li>
        <li v-if="!taskEvents.length" class="muted">이 작업의 사건이 아직 없습니다.</li>
      </ol>
    </section>

    <p v-if="!task && !artifact" class="muted">지도나 장면에서 작업을 선택하면 입력 명세·AC·아티팩트·사건이 여기에 표시됩니다.</p>

    <section class="block" aria-label="독립 검토">
      <h3>독립 검토 (각자 판정)</h3>
      <ReviewPair :pair="pair" @artifact="emit('artifact', $event)" />
      <details class="rounds-box">
        <summary>검토 회차 {{ snapshot.reports.length ? '' : '(없음)' }}</summary>
        <ReviewRounds :snapshot="snapshot" @artifact="emit('artifact', $event)" />
      </details>
    </section>
  </aside>
</template>

<style scoped>
.rounds-box summary { min-height: 36px; cursor: pointer; display: flex; align-items: center; }
.evidence { display: grid; gap: 14px; align-content: start; overflow: auto; }
.block { display: grid; gap: 6px; padding-bottom: 12px; border-bottom: 1px solid var(--line); }
.block:last-child { border-bottom: 0; }
h3 { font-size: 1rem; }
h4 { font-size: 0.85rem; color: var(--ink-3); margin-top: 6px; }
.raw { margin: 0; max-height: 260px; overflow: auto; padding: 8px; background: var(--surface-2); border-radius: 6px; font: 0.8rem/1.4 var(--mono); white-space: pre-wrap; }
.link {
  display: block; min-height: 36px; padding: 4px 0; border: 0; background: none; color: var(--focus);
  text-align: left; cursor: pointer; text-decoration: underline; text-underline-offset: 3px;
}
.link:disabled { color: var(--ink-3); text-decoration: none; cursor: default; }
</style>
