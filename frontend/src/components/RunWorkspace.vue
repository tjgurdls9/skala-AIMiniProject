<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ApiError } from '../api/errors'
import type { RunSource } from '../api/source'
import type { Task } from '../api/types'
import type { SendResult } from '../composables/useCommandForm'
import { useRelease } from '../composables/useRelease'
import { useRun, type CommandInput } from '../composables/useRun'
import { acIndex as indexAcceptance } from '../model/acceptance'
import { runAlerts, type AlertAction } from '../model/alerts'
import { deriveCurrentSprintId, orderedPhases, pendingApproval, sprintsOf, tallySprint, tasksOf } from '../model/derive'
import { RUN_STATE } from '../model/labels'
import AlertStrip from './AlertStrip.vue'
import BuildingRail, { type FloorEntry } from './BuildingRail.vue'
import ChangeDialog from './ChangeDialog.vue'
import EventLog from './EventLog.vue'
import EvidencePanel from './EvidencePanel.vue'
import OfficeScene from './OfficeScene.vue'
import PlanApprovalDialog from './PlanApprovalDialog.vue'
import PreviewDialog from './PreviewDialog.vue'
import ReleaseApprovalDialog from './ReleaseApprovalDialog.vue'
import RecordingExport from './RecordingExport.vue'
import ReleasePanel from './ReleasePanel.vue'
import RunHeader from './RunHeader.vue'
import SceneRoster from './SceneRoster.vue'
import SprintBoard from './SprintBoard.vue'
import StopDialog from './StopDialog.vue'
import WorkTree from './WorkTree.vue'

const props = defineProps<{ source: RunSource }>()
const emit = defineEmits<{ home: [] }>()

const run = useRun(props.source)
const snapshot = run.snapshot
const release = useRelease(props.source, snapshot, run.events)

// 화면 선택은 서버 필드가 아닌 view state. 스냅샷 교체·재연결로 초기화하지 않는다.
const view = reactive({ sprintId: null as string | null, taskId: null as string | null, artifactId: null as string | null })
const dialog = ref<'plan' | 'preview' | 'release' | 'change' | null>(null)
const stopAction = ref<'resume' | 'cancel' | null>(null)
const motion = ref(true)
const headerError = ref<ApiError | null>(null)
const announce = ref('')

const currentSprintId = computed(() => (snapshot.value ? deriveCurrentSprintId(snapshot.value) : null))
const sceneTasks = computed(() => (snapshot.value && view.sprintId ? snapshot.value.tasks.filter((t) => t.sprint_id === view.sprintId) : []))
const alerts = computed(() => (snapshot.value ? runAlerts(snapshot.value) : []))
const notices = computed(() => {
  const list: string[] = []
  if (run.loadError.value) list.push(`스냅샷을 읽지 못했습니다: ${run.loadError.value.message} (실행 상태가 바뀐 것은 아닙니다)`)
  if (run.notice.value) list.push(run.notice.value)
  if (headerError.value) list.push(`${headerError.value.message}`)
  return list
})
const acIndex = computed(() => indexAcceptance(run.acceptance.value))
const acNotice = computed(() => {
  if (run.acceptanceError.value) return `AC 판정을 읽지 못했습니다: ${run.acceptanceError.value.message} (이전 판정은 쓰지 않음)`
  if (run.acceptanceMismatch.value) return '판정의 명세 버전이 현재와 달라 표시하지 않습니다. 최신 판정을 다시 읽는 중입니다.'
  if (run.acceptancePending.value) return '현재 상태의 판정을 갱신하는 중입니다. 그동안 이전 판정은 표시하지 않습니다.'
  return null
})
const planApproval = computed(() => (snapshot.value ? pendingApproval(snapshot.value, 'plan') : null))
const releaseApproval = computed(() => (snapshot.value ? pendingApproval(snapshot.value, 'release') : null))
/** 사람의 결정을 기다리는 동안 장면에 점선 실루엣으로 보인다. 결정은 대화상자에서만 보낸다 */
const sceneWaiting = computed(() => {
  if (planApproval.value) return { text: '답 기다림 · 기획 승인', zone: 'meeting' as const }
  if (releaseApproval.value) return { text: '답 기다림 · 출시 승인', zone: 'release' as const }
  if (snapshot.value?.state === 'needs_input') return { text: '답 기다림 · 입력 필요', zone: 'meeting' as const }
  return null
})
const specArtifactId = computed(() => [...(snapshot.value?.artifacts ?? [])].reverse().find((a) => a.kind === 'spec')?.id ?? null)

// 최초 1회와 사용자가 아직 Sprint를 고르지 않았을 때만 현재 Sprint를 따라간다
watch(currentSprintId, (id) => {
  if (!view.sprintId) view.sprintId = id ?? snapshot.value?.sprints[0]?.id ?? null
}, { immediate: true })
watch(() => snapshot.value?.sprints.length, () => {
  if (!view.sprintId) view.sprintId = currentSprintId.value ?? snapshot.value?.sprints[0]?.id ?? null
})
watch(() => snapshot.value?.state, (state, prev) => {
  if (state && prev && state !== prev) {
    announce.value = `실행 상태: ${RUN_STATE[state].text}`
    headerError.value = null
  }
})
// 새로 생긴 결정 대기를 스크린리더에 한 번 알린다(사건 로그 전체를 읽히지 않음)
watch(() => alerts.value.filter((a) => a.action && a.action.kind !== 'task').map((a) => a.key).join(','), (keys, prev) => {
  const added = alerts.value.filter((a) => a.action && a.action.kind !== 'task' && !(prev ?? '').split(',').includes(a.key))
  if (keys && added.length) announce.value = added.map((a) => a.text).join(' · ')
})

function selectSprint(id: string): void {
  view.sprintId = id
}
function selectTask(id: string): void {
  const task = snapshot.value?.tasks.find((t) => t.id === id)
  if (task) view.sprintId = task.sprint_id
  view.taskId = id
  view.artifactId = null
}
function selectArtifact(id: string): void {
  view.artifactId = id
}

async function send(input: CommandInput, commandId: string): Promise<SendResult> {
  if (run.isReplay.value) return new ApiError(409, 'REPLAY_READ_ONLY', '실제 기록 재생에서는 명령을 보내지 않습니다.')
  try {
    await run.send(input, commandId)
    announce.value = '명령이 접수됐습니다. 반영은 실행 상태로 확인합니다.'
    return null
  } catch (error) {
    return error instanceof ApiError ? error : new ApiError(0, 'NETWORK', '명령을 보내지 못했습니다.')
  }
}

async function pause(): Promise<void> {
  headerError.value = await send({ action: 'pause', payload: {} }, crypto.randomUUID())
}

function act(action: AlertAction): void {
  if (action.kind === 'task') selectTask(action.taskId)
  else dialog.value = action.kind
}

// ── 건물형 사무실(사용자 디자인 지시): 실행 = 건물, Sprint = 층. 위층일수록 나중 단계 ──
const headerH = ref(64)
let headerObserver: ResizeObserver | null = null

/** 결정·문제 배너: 동작이 있는 알림만 고정 순서로(나머지는 오른쪽 패널) */
const actionAlerts = computed(() => alerts.value.filter((a) => a.action))

interface Floor extends FloorEntry { tasks: Task[]; goal: string }
const floors = computed<Floor[]>(() => {
  const s = snapshot.value
  if (!s) return []
  const byPhase = orderedPhases(s).flatMap((p) => sprintsOf(s, p.id))
  const ordered = byPhase.length === s.sprints.length ? byPhase : s.sprints
  const phaseTitle = new Map(s.phases.map((p) => [p.id, p.title]))
  return ordered
    .map((sprint, i): Floor => {
      const t = tallySprint(s, sprint)
      const tone = t.failed + t.blocked ? 'danger' : t.running ? 'active' : t.total && t.succeeded === t.total ? 'ok' : 'neutral'
      const problems = t.failed + t.blocked ? ` · 문제 ${t.failed + t.blocked}` : ''
      return {
        id: sprint.id, num: `${i + 1}F`, title: sprint.title, goal: sprint.goal, tone, tasks: tasksOf(s, sprint.id),
        sub: `${phaseTitle.get(sprint.phase_id) ?? ''} · 완료 ${t.succeeded}/${t.total}${problems}`,
      }
    })
    .reverse()
})
/** 결정 대기 실루엣은 현재 Sprint 층에만(없으면 고른 층) */
const ghostFloorId = computed(() => currentSprintId.value ?? view.sprintId)

onMounted(() => {
  void run.start()
  const header = document.querySelector<HTMLElement>('.run-header')
  if (header && 'ResizeObserver' in window) {
    headerObserver = new ResizeObserver(() => {
      headerH.value = Math.round(header.getBoundingClientRect().height)
    })
    headerObserver.observe(header)
  }
})
onBeforeUnmount(() => {
  run.dispose()
  headerObserver?.disconnect()
})
</script>

<template>
  <div class="workspace-root" :style="{ '--header-h': `${headerH}px` }">
    <RunHeader
      v-model:motion="motion"
      :kind="source.kind"
      :snapshot="snapshot"
      :connection="run.connection.value"
      :pending="run.pending.value"
      :is-replay="run.isReplay.value"
      @pause="pause"
      @resume="stopAction = 'resume'"
      @cancel="stopAction = 'cancel'"
      @reconnect="run.reconnect"
      @home="emit('home')"
    />
    <p class="sr-only" role="status" aria-live="polite">{{ announce }}</p>

    <div v-if="!snapshot" class="loading">
      <p v-if="run.loadError.value" class="error-box" role="alert">
        실행을 불러오지 못했습니다: {{ run.loadError.value.message }}
        <button type="button" class="btn small" @click="run.start">다시 시도</button>
      </p>
      <p v-else class="muted">실행 상태를 불러오는 중…</p>
    </div>

    <template v-else>
      <main id="workspace-main" class="office-page" tabindex="-1" aria-label="작업 공간">
        <BuildingRail class="rail-cell" :floors="floors" :selected-id="view.sprintId" :current-id="currentSprintId" :motion="motion" @select="selectSprint" />

        <div class="building-cell">
          <ul v-if="actionAlerts.length" class="plain decision-banner" aria-label="결정·문제 알림">
            <li v-for="a in actionAlerts" :key="a.key">
              <button type="button" :class="['banner-item', `tone-${a.tone}`]" @click="a.action && act(a.action)">
                <span class="banner-glyph" aria-hidden="true">{{ a.glyph }}</span>
                <span class="banner-text">{{ a.text }}</span>
                <span class="banner-go" aria-hidden="true">열기 →</span>
              </button>
            </li>
          </ul>

          <section
            v-for="f in floors"
            :id="`floor-${f.id}`"
            :key="f.id"
            class="floor"
            :class="{ selected: f.id === view.sprintId, current: f.id === currentSprintId }"
            :aria-label="`${f.num} ${f.title}`"
          >
            <button type="button" class="floor-head" :aria-pressed="f.id === view.sprintId" @click="selectSprint(f.id)">
                <span class="floor-line"><span class="floor-num">{{ f.num }}</span><span class="floor-name">{{ f.title }}</span><span v-if="f.id === currentSprintId" class="floor-now">현재 Sprint</span></span>
                <span class="floor-sub"><span :class="['dot', `tone-${f.tone}`]" aria-hidden="true" />{{ f.sub }}</span>
                <span class="floor-goal">{{ f.goal }}</span>
              </button>
            <div class="floor-box">
              <OfficeScene
                :tasks="f.tasks"
                :selected-task-id="view.taskId"
                :motion="motion"
                :subscribe="run.onLiveEvent"
                :waiting="f.id === ghostFloorId ? sceneWaiting : null"
                :doors-open="f.id === view.sprintId"
                :floor-label="f.num"
                @select="selectTask"
              />

              <p v-if="!f.tasks.length" class="floor-empty">아직 이 층에 배정된 작업이 없습니다</p>
            </div>
          </section>

          <section class="below-cell" aria-label="상세 작업 정보">
            <SprintBoard
              :snapshot="snapshot"
              :sprint-id="view.sprintId"
              :current-sprint-id="currentSprintId"
              :ac-index="acIndex"
              :ac-notice="acNotice"
              :is-replay="run.isReplay.value"
              @sprint="selectSprint"
              @artifact="selectArtifact"
            />
            <SceneRoster :tasks="sceneTasks" :selected-task-id="view.taskId" @select="selectTask" />
            <div class="below-split">
              <WorkTree
                :snapshot="snapshot"
                :sprint-id="view.sprintId"
                :task-id="view.taskId"
                :artifact-id="view.artifactId"
                :current-sprint-id="currentSprintId"
                @sprint="selectSprint"
                @task="selectTask"
                @artifact="selectArtifact"
              />
              <EventLog :events="run.events.value" :tasks="snapshot.tasks" @task="selectTask" />
            </div>
            <ReleasePanel :view="release.view.value" :error="release.error.value" :kind="source.kind" />
            <RecordingExport :source="source" :run-id="snapshot.run_id" />
          </section>
        </div>

        <aside class="side-cell" aria-label="결정·근거 패널">
          <AlertStrip :alerts="alerts" :notices="notices" @act="act" />
          <div v-if="planApproval || releaseApproval || ['preview_ready', 'needs_input', 'failed'].includes(snapshot.state)" class="decisions panel">
            <h2>내 결정</h2>
            <button v-if="planApproval" type="button" class="btn primary" @click="dialog = 'plan'">⚑ 기획 검토·승인</button>
            <button v-if="snapshot.state === 'preview_ready'" type="button" class="btn primary" @click="dialog = 'preview'">⚑ 프리뷰 확인·수정 요청</button>
            <button v-if="releaseApproval" type="button" class="btn primary" @click="dialog = 'release'">⚑ 배포 대상 검토·승인</button>
            <button v-if="['needs_input', 'failed'].includes(snapshot.state) && !run.isReplay.value" type="button" class="btn" @click="dialog = 'change'">수정 요청으로 다시 기획</button>
            <span v-if="run.isReplay.value" class="small muted">재생 중에는 내용만 확인할 수 있고 결정을 보낼 수 없습니다.</span>
          </div>
          <EvidencePanel
            :snapshot="snapshot"
            :events="run.events.value"
            :source="source"
            :task-id="view.taskId"
            :artifact-id="view.artifactId"
            :ac-index="acIndex"
            :ac-notice="acNotice"
            @task="selectTask"
            @artifact="selectArtifact"
          />
        </aside>
      </main>

      <PlanApprovalDialog
        :open="dialog === 'plan'"
        :approval="planApproval"
        :spec-artifact-id="specArtifactId"
        :source="source"
        :run-id="snapshot.run_id"
        :read-only="run.isReplay.value"
        :send="send"
        @close="dialog = null"
      />
      <PreviewDialog
        :open="dialog === 'preview'"
        :snapshot="snapshot"
        :source="source"
        :read-only="run.isReplay.value"
        :selected-artifact-id="view.artifactId"
        :send="send"
        @close="dialog = null"
        @artifact="selectArtifact"
      />
      <ReleaseApprovalDialog
        :open="dialog === 'release'"
        :approval="releaseApproval"
        :snapshot="snapshot"
        :source="source"
        :read-only="run.isReplay.value"
        :release-enabled="false"
        :send="send"
        @close="dialog = null"
        @artifact="selectArtifact"
      />
      <ChangeDialog v-if="!run.isReplay.value" :open="dialog === 'change'" :snapshot="snapshot" :send="send" @close="dialog = null" />
      <StopDialog :open="stopAction !== null" :action="stopAction" :send="send" @close="stopAction = null" />
    </template>
  </div>
</template>

<style scoped>
.loading { padding: calc(var(--header-h) + 32px) 16px 32px; }

/* 건물형 사무실: 왼쪽 층 목록 · 가운데 층 단면(위층부터) · 오른쪽 결정·근거 */
.office-page {
  --rail-w: 232px;
  --side-w: 380px;
  display: grid;
  grid-template-columns: var(--rail-w) minmax(0, 1fr) var(--side-w);
  grid-template-areas: "rail building side";
  gap: 16px;
  align-items: start;
  padding: calc(var(--header-h) + 12px) 16px 32px;
  background: var(--iso-bg);
  min-height: 100dvh;
  box-sizing: border-box;
}
.office-page:focus { outline: none; }
.rail-cell { grid-area: rail; position: sticky; top: calc(var(--header-h) + 12px); max-height: calc(100dvh - var(--header-h) - 24px); overflow: auto; }
.building-cell { grid-area: building; display: grid; gap: 16px; min-width: 0; }
.side-cell {
  grid-area: side;
  position: sticky;
  top: calc(var(--header-h) + 12px);
  max-height: calc(100dvh - var(--header-h) - 24px);
  overflow: auto;
  display: grid;
  gap: 12px;
  align-content: start;
}
.side-cell :deep(.alerts) { padding: 0; }

.decision-banner { display: grid; gap: 8px; }
.banner-item {
  width: 100%; min-height: var(--tap); display: flex; align-items: center; gap: 12px; padding: 10px 14px;
  border-radius: 16px; border: 1px solid #f4d7a8; background: #fff7ea; color: #3c2a10; font: inherit; text-align: left; cursor: pointer;
}
.banner-item:hover { filter: brightness(0.98); }
.banner-item.tone-danger { border-color: #f1b8b0; background: #fff1ee; color: #5a1a12; }
.banner-glyph { flex: 0 0 auto; width: 32px; height: 32px; border-radius: 50%; display: grid; place-items: center; background: #ffe7c2; font-weight: 700; }
.banner-item.tone-danger .banner-glyph { background: #ffd9d3; }
.banner-text { flex: 1 1 auto; font-weight: 650; font-size: 0.9rem; }
.banner-go { flex: 0 0 auto; font-size: 0.8rem; font-weight: 700; padding: 6px 12px; border-radius: 10px; background: #2f3370; color: #fff; }

.floor { scroll-margin-top: calc(var(--header-h) + 12px); }
.floor-box { position: relative; aspect-ratio: 960 / 580; border-radius: 18px; overflow: hidden; background: var(--iso-bg); }
.floor.selected .floor-box { box-shadow: 0 0 0 2px #f2a33a inset; }
.floor-head {
  display: flex; flex-direction: column; gap: 2px; max-width: 100%; margin: 0 0 4px 6px;
  padding: 4px 8px; border: 0; border-radius: 10px; background: transparent; color: var(--ink); font: inherit; text-align: left; cursor: pointer;
}
.floor-head:hover { background: color-mix(in srgb, var(--surface) 70%, transparent); }
.floor-line { display: flex; align-items: baseline; gap: 8px; }
.floor-num { font-size: clamp(20px, 2.4vw, 30px); font-weight: 750; color: #4a5a8a; letter-spacing: -0.02em; }
.floor-name { font-size: 14px; font-weight: 700; }
.floor-now { font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 999px; background: #fff1dc; color: #7a4300; }
.floor-sub { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--ink-3); }
.floor-goal { font-size: 11px; color: var(--ink-3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dot { width: 7px; height: 7px; border-radius: 50%; flex: 0 0 auto; background: var(--tone-neutral); }
.dot.tone-ok { background: var(--tone-ok); }
.dot.tone-active { background: var(--tone-active); }
.dot.tone-danger { background: var(--tone-danger); }
.floor-empty { position: absolute; left: 50%; bottom: 16px; transform: translateX(-50%); margin: 0; font-size: 12px; color: var(--ink-3); background: var(--surface); padding: 4px 12px; border-radius: 999px; }

.below-cell { display: grid; gap: 16px; min-width: 0; }
.below-split { display: grid; grid-template-columns: minmax(220px, 300px) minmax(0, 1fr); gap: 16px; align-items: start; }

.decisions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; border-left: 4px solid var(--tone-warn); }
.decisions h2 { margin-right: 8px; }

@media (max-width: 1180px) {
  .office-page { grid-template-columns: minmax(0, 1fr) 340px; grid-template-areas: "rail rail" "building side"; }
  .rail-cell { position: static; max-height: none; }
  .below-split { grid-template-columns: minmax(0, 1fr); }
}
/* 작은 화면: 층 목록 → 층 단면 → 결정·근거 */
@media (max-width: 860px) {
  .office-page { grid-template-columns: minmax(0, 1fr); grid-template-areas: "rail" "building" "side"; padding-inline: 10px; }
  .side-cell { position: static; max-height: none; overflow: visible; }
  .floor-goal { display: none; }
}
</style>
