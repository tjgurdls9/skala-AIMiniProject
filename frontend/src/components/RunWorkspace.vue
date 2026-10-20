<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ApiError } from '../api/errors'
import type { RunSource } from '../api/source'
import type { SendResult } from '../composables/useCommandForm'
import { useRun, type CommandInput } from '../composables/useRun'
import { runAlerts, type AlertAction } from '../model/alerts'
import { deriveCurrentSprintId, pendingApproval } from '../model/derive'
import { RUN_STATE } from '../model/labels'
import AlertStrip from './AlertStrip.vue'
import EventLog from './EventLog.vue'
import EvidencePanel from './EvidencePanel.vue'
import OfficeScene from './OfficeScene.vue'
import PlanApprovalDialog from './PlanApprovalDialog.vue'
import PreviewDialog from './PreviewDialog.vue'
import ReleaseApprovalDialog from './ReleaseApprovalDialog.vue'
import RunHeader from './RunHeader.vue'
import SprintBoard from './SprintBoard.vue'
import StopDialog from './StopDialog.vue'
import WorkTree from './WorkTree.vue'

const props = defineProps<{ source: RunSource }>()
const emit = defineEmits<{ home: [] }>()

const run = useRun(props.source)
const snapshot = run.snapshot

// 화면 선택은 서버 필드가 아닌 view state. 스냅샷 교체·재연결로 초기화하지 않는다.
const view = reactive({ sprintId: null as string | null, taskId: null as string | null, artifactId: null as string | null })
const dialog = ref<'plan' | 'preview' | 'release' | null>(null)
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
  if (props.source.kind === 'example') list.push('합성 예시입니다. 명령을 보내지 않으며 외부 승인·배포가 실행되지 않습니다.')
  if (headerError.value) list.push(`${headerError.value.message}`)
  return list
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

onMounted(() => void run.start())
onBeforeUnmount(() => run.dispose())
</script>

<template>
  <div class="workspace-root">
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
      <AlertStrip :alerts="alerts" :notices="notices" @act="act" />
      <main id="workspace-main" class="workspace" tabindex="-1" aria-label="작업 공간">
        <WorkTree
          class="area-tree"
          :snapshot="snapshot"
          :sprint-id="view.sprintId"
          :task-id="view.taskId"
          :artifact-id="view.artifactId"
          :current-sprint-id="currentSprintId"
          @sprint="selectSprint"
          @task="selectTask"
          @artifact="selectArtifact"
        />
        <div class="area-center">
          <SprintBoard :snapshot="snapshot" :sprint-id="view.sprintId" :current-sprint-id="currentSprintId" @sprint="selectSprint" />
          <OfficeScene
            :tasks="sceneTasks"
            :selected-task-id="view.taskId"
            :motion="motion"
            :subscribe="run.onLiveEvent"
            @select="selectTask"
          />
          <div v-if="planApproval || releaseApproval || snapshot.state === 'preview_ready'" class="decisions panel">
            <h2>내 결정</h2>
            <button v-if="planApproval" type="button" class="btn primary" @click="dialog = 'plan'">⚑ 기획 검토·승인</button>
            <button v-if="snapshot.state === 'preview_ready'" type="button" class="btn primary" @click="dialog = 'preview'">⚑ 프리뷰 확인·수정 요청</button>
            <button v-if="releaseApproval" type="button" class="btn primary" @click="dialog = 'release'">⚑ 배포 대상 검토·승인</button>
            <span v-if="run.isReplay.value" class="small muted">재생 중에는 내용만 확인할 수 있고 결정을 보낼 수 없습니다.</span>
          </div>
        </div>
        <EvidencePanel
          class="area-evidence"
          :snapshot="snapshot"
          :events="run.events.value"
          :source="source"
          :task-id="view.taskId"
          :artifact-id="view.artifactId"
          @task="selectTask"
          @artifact="selectArtifact"
        />
        <EventLog class="area-log" :events="run.events.value" :tasks="snapshot.tasks" @task="selectTask" />
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
      <StopDialog :open="stopAction !== null" :action="stopAction" :send="send" @close="stopAction = null" />
    </template>
  </div>
</template>

<style scoped>
.loading { padding: 32px 16px; }
.workspace {
  display: grid; gap: var(--gap); padding: 12px 16px 24px;
  grid-template-columns: minmax(220px, 280px) minmax(0, 1fr) minmax(280px, 380px);
  grid-template-areas:
    "tree center evidence"
    "tree log evidence";
  align-items: start;
}
.area-tree { grid-area: tree; position: sticky; top: 84px; max-height: calc(100dvh - 100px); }
.area-center { grid-area: center; display: grid; gap: var(--gap); min-width: 0; }
.area-evidence { grid-area: evidence; position: sticky; top: 84px; max-height: calc(100dvh - 100px); }
.area-log { grid-area: log; }
.decisions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; border-left: 4px solid var(--tone-warn); }
.decisions h2 { margin-right: 8px; }
@media (max-width: 1240px) {
  .workspace {
    grid-template-columns: minmax(200px, 250px) minmax(0, 1fr);
    grid-template-areas: "tree center" "tree evidence" "log log";
  }
  .area-evidence { position: static; max-height: none; }
}
/* 작은 화면: 장면 → 현재 작업·결정 → 근거 → 지도 → 기록 */
@media (max-width: 820px) {
  .workspace { grid-template-columns: minmax(0, 1fr); grid-template-areas: "center" "evidence" "tree" "log"; padding: 8px 16px 24px; }
  .area-tree { position: static; max-height: none; }
}
</style>
