<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ApiError } from '../api/errors'
import type { RunSource } from '../api/source'
import type { Task } from '../api/types'
import type { SendResult } from '../composables/useCommandForm'
import { useElevator } from '../composables/useElevator'
import { useFloorSelection } from '../composables/useFloorSelection'
import { useRelease } from '../composables/useRelease'
import { useRun, type CommandInput } from '../composables/useRun'
import { useSnapScroll } from '../composables/useSnapScroll'
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

// 모션 감소 설정이면 엘리베이터 연출 없이 바로 전환한다
const reducedMq = typeof window.matchMedia === 'function' ? window.matchMedia('(prefers-reduced-motion: reduce)') : null
const prefersReduced = ref(reducedMq?.matches ?? false)
const onReducedChange = (): void => {
  prefersReduced.value = reducedMq?.matches ?? false
}
const effectiveMotion = computed(() => motion.value && !prefersReduced.value)

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

// 층(Sprint) 선택: 직접 고른 적이 없을 때만 현재 Sprint를 따라가고, 고른 뒤에는 알림만 띄운다
const firstSprintId = computed(() => snapshot.value?.sprints[0]?.id ?? null)
const selection = useFloorSelection({ currentId: currentSprintId, firstId: firstSprintId })
watch(selection.selectedId, (id) => {
  view.sprintId = id
}, { immediate: true })
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
  selection.pick(id)
}
function selectTask(id: string): void {
  const task = snapshot.value?.tasks.find((t) => t.id === id)
  if (task && task.sprint_id !== view.sprintId) selection.pick(task.sprint_id)
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

// ── 건물형 사무실(사용자 디자인 지시: 컷 A) ──
// 처음에는 현재 층 단면이 화면 전체를 채우고, 충분히 누적된 스크롤·드래그(저항)로 줄어들며 상세가 드러난다.
/** 상세 상태의 스크롤 위치(화면 높이 비율). 축소 애니메이션의 길이이기도 하다 */
const SHRINK_RATIO = 0.55
const HERO_ALERT_LIMIT = 3
const headerH = ref(64)
const shrinkPx = ref(Math.max(1, Math.round(window.innerHeight * SHRINK_RATIO)))
let headerObserver: ResizeObserver | null = null

const snap = useSnapScroll({ distance: () => shrinkPx.value, reducedMotion: () => prefersReduced.value })
const progress = snap.progress

function onResize(): void {
  shrinkPx.value = Math.max(1, Math.round(window.innerHeight * SHRINK_RATIO))
}
function scrollToDetails(): void {
  snap.commit('detail')
}

/** 전체 화면일 때 사무실 위에 띄울 결정·문제 알림(고정 순서, 나머지는 패널) */
const heroAlerts = computed(() => alerts.value.filter((a) => a.action).slice(0, HERO_ALERT_LIMIT))

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
const floorOrder = computed(() => floors.value.map((f) => f.id))
const elevator = useElevator({ target: selection.selectedId, order: () => floorOrder.value, motion: () => effectiveMotion.value })
/** 화면에 보이는 층: 엘리베이터 문이 열릴 때 바뀐다 */
const shownFloor = computed(() => floors.value.find((f) => f.id === elevator.shownId.value) ?? floors.value.find((f) => f.id === selection.selectedId.value) ?? floors.value[0] ?? null)
const inTransit = computed(() => elevator.phase.value === 'closing' || elevator.phase.value === 'moving')
/** 결정 대기 실루엣은 현재 Sprint 층에만(없으면 고른 층) */
const ghostFloorId = computed(() => currentSprintId.value ?? view.sprintId)
const followNotice = computed(() => floors.value.find((f) => f.id === selection.notice.value) ?? null)
function goToNotice(): void {
  if (followNotice.value) selection.pick(followNotice.value.id)
}

onMounted(() => {
  void run.start()
  window.addEventListener('resize', onResize)
  reducedMq?.addEventListener?.('change', onReducedChange)
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
  window.removeEventListener('resize', onResize)
  reducedMq?.removeEventListener?.('change', onReducedChange)
  headerObserver?.disconnect()
})
</script>

<template>
  <div class="workspace-root" :style="{ '--p': progress.toFixed(3), '--header-h': `${headerH}px`, '--shrink-px': `${shrinkPx}px` }">
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
        <section class="scene-cell" :class="{ 'in-transit': inTransit }" aria-label="현재 층 사무실">
          <OfficeScene
            v-if="shownFloor"
            :key="shownFloor.id"
            :tasks="shownFloor.tasks"
            :selected-task-id="view.taskId"
            :motion="effectiveMotion"
            :subscribe="run.onLiveEvent"
            :waiting="shownFloor.id === ghostFloorId ? sceneWaiting : null"
            :doors-open="elevator.doorsOpen.value"
            :floor-label="shownFloor.num"
            @select="selectTask"
          />
          <BuildingRail
            class="rail-overlay"
            :floors="floors"
            :selected-id="view.sprintId"
            :current-id="currentSprintId"
            :cab-id="elevator.cabId.value"
            :display-id="elevator.displayId.value"
            :direction="elevator.direction.value"
            :ride-ms="elevator.rideMs.value"
            @select="selectSprint"
          />
          <div v-if="shownFloor" class="floor-title" :class="{ gone: progress > 0.6 }" :aria-hidden="progress > 0.6">
            <span class="title-line"><span class="floor-num">{{ shownFloor.num }}</span><span class="floor-name">{{ shownFloor.title }}</span><span v-if="shownFloor.id === currentSprintId" class="floor-now">현재 Sprint</span></span>
            <span class="title-sub">{{ shownFloor.sub }}</span>
            <span class="title-goal">{{ shownFloor.goal }}</span>
          </div>
          <ul class="plain scene-alerts" :class="{ gone: progress > 0.6 }" :aria-hidden="progress > 0.6" aria-label="결정·문제 알림">
            <li v-if="followNotice" class="follow-chip">
              <span class="chip-glyph" aria-hidden="true">↕</span>
              <span class="chip-text">현재 Sprint가 {{ followNotice.num }}로 바뀜 · {{ followNotice.title }}</span>
              <button type="button" class="go" @click="goToNotice">이동</button>
              <button type="button" class="close" aria-label="알림 닫기" @click="selection.dismiss()">✕</button>
            </li>
            <li v-for="a in heroAlerts" :key="a.key">
              <button type="button" :class="['alert-chip', `tone-${a.tone}`]" @click="a.action && act(a.action)">
                <span class="chip-glyph" aria-hidden="true">{{ a.glyph }}</span>
                <span class="chip-text">{{ a.text }}</span>
                <span class="chip-go" aria-hidden="true">열기 →</span>
              </button>
            </li>
            <li v-if="alerts.length > heroAlerts.length" class="more-chip">외 {{ alerts.length - heroAlerts.length }}건 · 아래 패널</li>
          </ul>
          <button type="button" class="scroll-cue" :tabindex="progress > 0.5 ? -1 : 0" @click="scrollToDetails">
            상세 작업 정보 <span aria-hidden="true">↓</span>
          </button>
        </section>

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

/*
 * 처음에는 현재 층 단면이 화면 전체를 채운다(컷 A). 스크롤 진행도 --p(0→1)에 따라 줄어들며
 * 오른쪽 결정·근거 패널과 아래 상세 정보가 드러난다. 엘리베이터는 장면 왼쪽에 항상 붙어 있다.
 */
.office-page {
  --side-w: 380px;
  --gap-p: calc(16px * var(--p));
  display: grid;
  grid-template-columns: minmax(0, 1fr) var(--side-w);
  grid-template-areas: "scene side" "below side";
  column-gap: 16px;
  row-gap: 16px;
  align-items: start;
  /* 축소 구간에서는 스크롤만큼 위 여백을 늘려 사무실을 화면에 고정한다(축소가 끝나면 함께 스크롤) */
  padding: calc((var(--shrink-px) + var(--header-h) + 12px) * var(--p)) var(--gap-p) 32px;
  overflow-anchor: none;
  background: var(--iso-bg);
}
.office-page:focus { outline: none; }

.scene-cell {
  grid-area: scene;
  position: relative;
  z-index: 2;
  height: calc(100dvh - (100dvh - var(--scene-min, 60vh)) * var(--p));
  /* p=0이면 오른쪽 패널 위까지 덮어 화면 전체를 채운다 */
  margin-right: calc((var(--side-w) + 16px + var(--gap-p)) * (var(--p) - 1));
  border-radius: calc(14px * var(--p));
  overflow: hidden;
  background: var(--iso-bg);
}
/* 전체 화면일 때 장면은 떠 있는 헤더 아래부터, 왼쪽 엘리베이터 오른쪽부터 그린다 */
.scene-cell :deep(.stage) { top: calc(var(--header-h) * (1 - var(--p))); left: 128px; transition: opacity 260ms; }
.scene-cell.in-transit :deep(.stage) { opacity: 0.55; }

.rail-overlay { position: absolute; left: 16px; top: calc(var(--header-h) * (1 - var(--p)) + 16px); z-index: 3; max-height: calc(100% - var(--header-h) * (1 - var(--p)) - 32px); overflow: auto; }

.floor-title {
  position: absolute; left: 144px; top: calc(var(--header-h) * (1 - var(--p)) + 12px); z-index: 3; display: flex; flex-direction: column; gap: 2px; max-width: 34%;
  pointer-events: none; opacity: clamp(0, calc(1 - var(--p) * 1.6), 1);
}
.floor-title.gone { visibility: hidden; }
.title-line { display: flex; align-items: baseline; gap: 8px; }
.floor-num { font-size: clamp(22px, 2.6vw, 32px); font-weight: 750; color: #4a5a8a; letter-spacing: -0.02em; }
.floor-name { font-size: 14px; font-weight: 700; }
.floor-now { font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 999px; background: #fff1dc; color: #7a4300; }
.title-sub, .title-goal { font-size: 11px; color: var(--ink-3); }

/* 우상단 알림(컷 B에서 가져옴): 현재 Sprint 변화와 결정·문제 */
.scene-alerts {
  position: absolute; right: 16px; top: calc(var(--header-h) * (1 - var(--p)) + 12px); z-index: 3; display: grid; gap: 8px; justify-items: end; max-width: min(380px, 44%);
  opacity: clamp(0, calc(1 - var(--p) * 1.6), 1);
}
.scene-alerts.gone { visibility: hidden; }
.scene-alerts > li { width: 100%; }
.alert-chip, .follow-chip {
  width: 100%; min-height: var(--tap); box-sizing: border-box; display: flex; align-items: center; gap: 10px; padding: 8px 12px;
  border-radius: 14px; border: 1px solid #f4d7a8; background: #fff7ea; color: #3c2a10; font: inherit; font-size: 0.85rem; text-align: left;
  box-shadow: 0 2px 10px var(--iso-shadow);
}
.alert-chip { cursor: pointer; }
.alert-chip:hover { filter: brightness(0.98); }
.alert-chip.tone-danger { border-color: #f1b8b0; background: #fff1ee; color: #5a1a12; }
.follow-chip { border-color: #c9cdf0; background: #eef0fc; color: #252a5a; }
.chip-glyph { flex: 0 0 auto; width: 28px; height: 28px; border-radius: 50%; display: grid; place-items: center; background: #ffe7c2; font-weight: 700; }
.alert-chip.tone-danger .chip-glyph { background: #ffd9d3; }
.follow-chip .chip-glyph { background: #dfe3fb; }
.chip-text { flex: 1 1 auto; font-weight: 650; min-width: 0; }
.chip-go, .follow-chip .go { flex: 0 0 auto; font-size: 0.78rem; font-weight: 700; padding: 6px 12px; border-radius: 10px; background: #2f3370; color: #fff; border: 0; font-family: inherit; cursor: pointer; }
.follow-chip .close { flex: 0 0 auto; width: 32px; height: 32px; border: 0; border-radius: 8px; background: transparent; color: inherit; cursor: pointer; }
.follow-chip .close:hover { background: #dfe3fb; }
.more-chip { font-size: 0.78rem; color: var(--ink-3); background: var(--surface); padding: 4px 12px; border-radius: 999px; width: auto !important; }

.scroll-cue {
  position: absolute; left: 50%; bottom: 20px; transform: translateX(-50%); z-index: 3;
  min-height: var(--tap); padding: 0 20px; border-radius: 999px; border: 0;
  background: #2f3370; color: #fff; font-weight: 700; cursor: pointer; box-shadow: 0 4px 14px var(--iso-shadow);
  opacity: calc(1 - var(--p) * 2);
  pointer-events: auto;
}

.side-cell {
  grid-area: side;
  position: sticky;
  top: calc(var(--header-h) + 12px);
  max-height: calc(100dvh - var(--header-h) - 24px);
  overflow: auto;
  display: grid;
  gap: 12px;
  align-content: start;
  z-index: 1;
  opacity: clamp(0, calc(var(--p) * 1.6 - 0.4), 1);
}
.side-cell :deep(.alerts) { padding: 0; }

.below-cell {
  grid-area: below;
  display: grid;
  gap: 16px;
  min-width: 0;
  opacity: clamp(0, calc(var(--p) * 2 - 0.6), 1);
}
.below-split { display: grid; grid-template-columns: minmax(220px, 300px) minmax(0, 1fr); gap: 16px; align-items: start; }

.decisions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; border-left: 4px solid var(--tone-warn); }
.decisions h2 { margin-right: 8px; }

@media (max-width: 1100px) {
  .office-page { --side-w: 320px; }
  .below-split { grid-template-columns: minmax(0, 1fr); }
}
/* 작은 화면: 장면 → 결정·근거 → 상세. 엘리베이터는 장면 아래 가로 줄 */
@media (max-width: 860px) {
  .office-page { grid-template-columns: minmax(0, 1fr); grid-template-areas: "scene" "side" "below"; }
  .scene-cell { margin-right: 0; --scene-min: 56vh; }
  .scene-cell :deep(.stage) { left: 0; bottom: calc(88px + 64px * (1 - var(--p))); }
  .rail-overlay { left: 10px; right: 10px; top: auto; bottom: 72px; max-height: none; }
  .rail-overlay :deep(.elevator-display) { flex: 0 0 auto; }
  .floor-title { left: 12px; max-width: 60%; }
  .title-goal { display: none; }
  .scene-alerts { max-width: 60%; }
  .scene-alerts > li:nth-child(n + 2):not(.follow-chip) { display: none; }
  .side-cell { position: static; max-height: none; overflow: visible; }
}
</style>
