<script setup lang="ts">
import { computed } from 'vue'
import type { AcceptanceItem, Snapshot } from '../api/types'
import { AC_STATE, tallyAc } from '../model/acceptance'
import { orderedPhases, sprintsOf, tallySprint } from '../model/derive'
import AcceptanceList from './AcceptanceList.vue'

/** Phase 경로 위의 Sprint 집계 지도 + 선택 Sprint 목표. 작업 수 진행과 AC를 따로 보여준다. 임의 완료율·예상 시간 없음. */
const props = defineProps<{
  snapshot: Snapshot
  sprintId: string | null
  currentSprintId: string | null
  acIndex: ReadonlyMap<string, AcceptanceItem>
  /** 판정을 쓸 수 없는 이유(읽기 실패·명세 전환 중). null이면 정상 */
  acNotice: string | null
  isReplay: boolean
}>()
const emit = defineEmits<{ sprint: [id: string]; artifact: [id: string] }>()

const path = computed(() =>
  orderedPhases(props.snapshot).map((phase) => ({
    phase,
    sprints: sprintsOf(props.snapshot, phase.id).map((s) => ({ s, tally: tallySprint(props.snapshot, s) })),
  })),
)
const selected = computed(() => props.snapshot.sprints.find((s) => s.id === props.sprintId) ?? null)
const tally = computed(() => (selected.value ? tallySprint(props.snapshot, selected.value) : null))
const acTally = computed(() => (selected.value ? tallyAc(props.acIndex, selected.value.acceptance_ids) : null))
</script>

<template>
  <section class="board panel" aria-labelledby="board-title">
    <h2 id="board-title" class="sr-only">Phase·Sprint 지도</h2>
    <ol class="plain path">
      <li v-for="{ phase, sprints } in path" :key="phase.id" class="phase">
        <span class="phase-name small">{{ phase.title }}</span>
        <div class="sprints">
          <button
            v-for="{ s, tally: t } in sprints"
            :key="s.id"
            type="button"
            :class="['cell', { current: s.id === currentSprintId }]"
            :aria-pressed="s.id === sprintId"
            :aria-label="`${s.title}: 완료 ${t.succeeded}/${t.total}, 진행 ${t.running}, 문제 ${t.failed + t.blocked}`"
            @click="emit('sprint', s.id)"
          >
            <span class="cell-title">{{ s.title.split('·')[0].trim() }}</span>
            <span class="bar" aria-hidden="true">
              <span class="seg ok" :style="{ flexGrow: t.succeeded }" />
              <span class="seg active" :style="{ flexGrow: t.running }" />
              <span class="seg danger" :style="{ flexGrow: t.failed + t.blocked }" />
              <span class="seg rest" :style="{ flexGrow: Math.max(0, t.total - t.succeeded - t.running - t.failed - t.blocked) }" />
            </span>
            <span class="small">{{ t.succeeded }}/{{ t.total }}<template v-if="t.failed + t.blocked"> · ✕{{ t.failed + t.blocked }}</template></span>
          </button>
        </div>
      </li>
    </ol>

    <div v-if="selected && tally" class="goal">
      <div>
        <p class="small muted">
          선택한 Sprint<template v-if="selected.id === currentSprintId"> · 현재 Sprint(작업 상태에서 도출)</template>
        </p>
        <h3 class="goal-title">{{ selected.title }}</h3>
        <p>{{ selected.goal }}</p>
      </div>
      <dl class="kv small counts">
        <dt>작업 진행</dt>
        <dd>완료 {{ tally.succeeded }} / 계획 {{ tally.total }} · 진행 {{ tally.running }} · 대기 {{ tally.waiting }}<template v-if="tally.closed"> · 취소·대체 {{ tally.closed }}</template></dd>
        <dt>문제</dt>
        <dd :class="tally.failed + tally.blocked ? 'tone-danger' : ''">실패 {{ tally.failed }} · 차단 {{ tally.blocked }}</dd>
        <dt>인수 기준</dt>
        <dd>
          <span v-if="acTally">
            {{ tally.acceptanceCount }}개 중
            <span class="tone-ok">{{ AC_STATE.met.glyph }} 충족 {{ acTally.met }}</span>
            · <span :class="acTally.failed ? 'tone-danger' : ''">{{ AC_STATE.failed.glyph }} 실패 {{ acTally.failed }}</span>
            · 미충족 {{ acTally.unmet }}<template v-if="acTally.not_run"> · 미실행 {{ acTally.not_run }}</template><template v-if="acTally.unknown"> · 판정 없음 {{ acTally.unknown }}</template>
          </span>
          <span class="small muted">· 서버 판정{{ isReplay ? '(기록 당시 동결)' : '' }}, 작업 완료 수와 별개</span>
          <p v-if="acNotice" class="small tone-warn">{{ acNotice }}</p>
          <AcceptanceList :ids="selected.acceptance_ids" :index="acIndex" :reports="snapshot.reports" @artifact="emit('artifact', $event)" />
        </dd>
      </dl>
    </div>
    <p v-else class="muted">Sprint가 아직 없습니다. 기획이 승인되면 작업 계획이 표시됩니다.</p>
  </section>
</template>

<style scoped>
.board { display: grid; gap: 14px; }
.path { display: flex; gap: 0; overflow-x: auto; padding-bottom: 6px; }
.phase { display: grid; gap: 6px; flex: 1 0 auto; position: relative; padding-right: 22px; }
/* Phase 사이를 잇는 진행선 */
.phase:not(:last-child)::after {
  content: ""; position: absolute; right: 4px; top: 50%; width: 14px; height: 2px;
  background: repeating-linear-gradient(90deg, var(--ink-3) 0 4px, transparent 4px 7px);
}
.phase-name { color: var(--ink-3); font-weight: 600; }
.sprints { display: flex; gap: 6px; }
.cell {
  min-width: 104px; min-height: var(--tap); display: grid; gap: 6px; padding: 8px 10px; text-align: left;
  border: 1px solid color-mix(in srgb, var(--line) 85%, transparent); border-radius: 12px; background: var(--surface); cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.cell:hover { transform: translateY(-2px); box-shadow: 0 10px 22px -14px rgb(20 30 50 / 0.5); }
.cell[aria-pressed="true"] { border-color: var(--focus); box-shadow: 0 0 0 3px color-mix(in srgb, var(--focus) 22%, transparent); }
.cell.current { background: linear-gradient(180deg, color-mix(in srgb, var(--tone-active) 10%, var(--surface)), var(--surface)); }
.cell.current .cell-title::after { content: " ●"; color: var(--tone-active); }
.cell-title { font-size: 0.85rem; font-weight: 600; }
.bar { display: flex; height: 8px; border-radius: 4px; overflow: hidden; background: var(--surface-2); box-shadow: inset 0 1px 2px rgb(0 0 0 / 0.12); }
.seg.ok { background: var(--tone-ok); }
.seg.active { background: var(--tone-active); }
.seg.danger { background: var(--tone-danger); }
.seg.rest { background: var(--line); }
.goal { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.1fr); gap: 12px 20px; }
.goal-title { font-size: 1.35rem; font-weight: 850; letter-spacing: -0.02em; margin: 2px 0 6px; }
@media (max-width: 900px) { .goal { grid-template-columns: 1fr; } }
</style>
