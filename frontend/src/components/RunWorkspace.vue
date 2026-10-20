<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ApiError } from '../api/errors'
import type { RunSource } from '../api/source'
import type { SendResult } from '../composables/useCommandForm'
import { useRun, type CommandInput } from '../composables/useRun'
import { useSnapScroll } from '../composables/useSnapScroll'
import { acIndex as indexAcceptance } from '../model/acceptance'
import { runAlerts, type AlertAction } from '../model/alerts'
import { deriveCurrentSprintId, pendingApproval } from '../model/derive'
import { RUN_STATE } from '../model/labels'
import AlertStrip from './AlertStrip.vue'
import ChangeDialog from './ChangeDialog.vue'
import EventLog from './EventLog.vue'
import EvidencePanel from './EvidencePanel.vue'
import OfficeScene from './OfficeScene.vue'
import PlanApprovalDialog from './PlanApprovalDialog.vue'
import PreviewDialog from './PreviewDialog.vue'
import ReleaseApprovalDialog from './ReleaseApprovalDialog.vue'
import RunHeader from './RunHeader.vue'
import SceneRoster from './SceneRoster.vue'
import SprintBoard from './SprintBoard.vue'
import StopDialog from './StopDialog.vue'
import WorkTree from './WorkTree.vue'

const props = defineProps<{ source: RunSource }>()
const emit = defineEmits<{ home: [] }>()

const run = useRun(props.source)
const snapshot = run.snapshot

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

// ── 전체 화면 사무실 ↔ 상세: 저항 있는 두 상태 전환 ──
/** 상세 상태의 스크롤 위치(화면 높이 비율). 축소 애니메이션의 길이이기도 하다 */
const SHRINK_RATIO = 0.55
const HERO_ALERT_LIMIT = 3
const headerH = ref(64)
const shrinkPx = ref(Math.max(1, Math.round(window.innerHeight * SHRINK_RATIO)))
let headerObserver: ResizeObserver | null = null

const snap = useSnapScroll({ distance: () => shrinkPx.value })
const progress = snap.progress

function onResize(): void {
  shrinkPx.value = Math.max(1, Math.round(window.innerHeight * SHRINK_RATIO))
}
function scrollToDetails(): void {
  snap.commit('detail')
}

/** 전체 화면일 때 사무실 위에 띄울 결정·문제 알림(고정 순서, 나머지는 패널) */
const heroAlerts = computed(() => alerts.value.filter((a) => a.action).slice(0, HERO_ALERT_LIMIT))
const sceneSprint = computed(() => snapshot.value?.sprints.find((sp) => sp.id === view.sprintId) ?? null)

onMounted(() => {
  void run.start()
  window.addEventListener('resize', onResize)
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
        <section class="scene-cell" aria-label="사무실 장면">
          <OfficeScene
            :tasks="sceneTasks"
            :selected-task-id="view.taskId"
            :motion="motion"
            :subscribe="run.onLiveEvent"
            @select="selectTask"
          />
          <div class="scene-hud" :class="{ gone: progress > 0.6 }" :aria-hidden="progress > 0.6">
            <p v-if="sceneSprint" class="hud-chip sprint">
              <strong>{{ sceneSprint.title }}</strong>
              <span>{{ sceneSprint.goal }}</span>
            </p>
            <ul v-if="heroAlerts.length" class="plain hud-alerts" aria-label="결정·문제 알림">
              <li v-for="a in heroAlerts" :key="a.key">
                <button type="button" :class="['hud-chip', 'alert', `tone-${a.tone}`]" @click="a.action && act(a.action)">
                  <span aria-hidden="true">{{ a.glyph }}</span> {{ a.text }}
                </button>
              </li>
              <li v-if="alerts.length > heroAlerts.length" class="hud-chip more">외 {{ alerts.length - heroAlerts.length }}건 · 아래 패널</li>
            </ul>
          </div>
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
 * 처음에는 사무실이 화면 전체를 채운다. 스크롤 진행도 --p(0→1)에 따라 사무실이 줄어들고
 * 오른쪽 패널(고정 폭, 내용이 찌그러지지 않음)과 아래 상세 정보가 드러난다.
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

/* 사무실 위 정보(전체 화면일 때 특히 중요) */
.scene-hud {
  position: absolute;
  inset: calc(var(--header-h) * (1 - var(--p)) + 12px) 12px auto 12px;
  display: flex; flex-wrap: wrap; gap: 8px; align-items: flex-start; justify-content: space-between;
  pointer-events: none;
  /* 축소되면 같은 정보가 오른쪽 패널에 있으므로 사라진다 */
  opacity: clamp(0, calc(1 - var(--p) * 1.6), 1);
}
.scene-hud.gone { visibility: hidden; }
/* 전체 화면일 때 장면은 떠 있는 헤더 아래부터 그린다 */
.scene-cell :deep(.stage) { top: calc(var(--header-h) * (1 - var(--p))); }
.hud-chip {
  pointer-events: auto;
  display: inline-flex; flex-direction: column; gap: 2px;
  max-width: min(520px, 100%);
  padding: 8px 12px; border-radius: 10px;
  background: #14181d; color: #f2efe6;
  border: 1px solid #2c333a;
  font-size: 0.875rem; text-align: left;
}
.hud-chip.sprint strong { font-size: 0.95rem; }
.hud-chip.sprint span { font-size: 0.85rem; opacity: 0.8; }
.hud-alerts { display: grid; gap: 6px; justify-items: end; }
.hud-chip.alert { flex-direction: row; gap: 8px; min-height: var(--tap); align-items: center; cursor: pointer; font-weight: 650; border-left: 4px solid currentColor; }
.hud-chip.alert.tone-danger { color: #ffb4a8; }
.hud-chip.alert.tone-warn { color: #ffd27a; }
.hud-chip.alert.tone-wait { color: #c9c4ff; }
.hud-chip.alert:hover { filter: brightness(1.05); }
.hud-chip.more { font-size: 0.8rem; }

.scroll-cue {
  position: absolute; left: 50%; bottom: 20px; transform: translateX(-50%);
  min-height: var(--tap); padding: 0 18px; border-radius: 999px; border: 1px solid #2c333a;
  background: #14181d; color: #f2efe6; font-weight: 700; cursor: pointer;
  opacity: calc(1 - var(--p) * 2);
  pointer-events: auto;
}

@media (max-width: 1100px) {
  .office-page { --side-w: 320px; }
  .below-split { grid-template-columns: minmax(0, 1fr); }
}
/* 작은 화면: 장면 → 결정·근거 → 상세 */
@media (max-width: 860px) {
  .office-page { grid-template-columns: minmax(0, 1fr); grid-template-areas: "scene" "side" "below"; }
  .scene-cell { margin-right: 0; --scene-min: 52vh; }
  .side-cell { position: static; max-height: none; overflow: visible; }
  .hud-alerts { justify-items: start; }
  /* 작은 화면: 칩은 아래쪽에 작게, 사무실 가운데를 가리지 않게 */
  .scene-hud { inset: auto 10px 72px 10px; flex-direction: column-reverse; align-items: stretch; }
  .hud-chip { font-size: 0.8rem; padding: 6px 10px; }
  .hud-chip.sprint span { display: none; }
  .hud-alerts li:nth-child(n + 2):not(.more) { display: none; }
}
</style>
