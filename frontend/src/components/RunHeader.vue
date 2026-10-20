<script setup lang="ts">
import { computed } from 'vue'
import type { SourceKind } from '../api/source'
import type { Snapshot } from '../api/types'
import type { ConnectionState, PendingCommand } from '../composables/useRun'
import { acceptsCommands, RESUMABLE_STATES } from '../model/derive'
import { RUN_STATE, shortId } from '../model/labels'
import SourceBadge from './SourceBadge.vue'
import ThemeControls from './ThemeControls.vue'

const props = defineProps<{
  kind: SourceKind
  snapshot: Snapshot | null
  connection: ConnectionState
  pending: PendingCommand | null
  isReplay: boolean
  motion: boolean
}>()
const emit = defineEmits<{ pause: []; resume: []; cancel: []; reconnect: []; home: []; 'update:motion': [value: boolean] }>()

const CONNECTION: Record<ConnectionState, { text: string; tone: string }> = {
  idle: { text: '연결 전', tone: 'neutral' },
  connecting: { text: '연결 중', tone: 'active' },
  open: { text: '사건 수신 중', tone: 'ok' },
  reconnecting: { text: '연결 끊김 · 자동 재연결 중', tone: 'warn' },
  resyncing: { text: '다시 동기화 중', tone: 'warn' },
  closed: { text: '연결 끊김', tone: 'danger' },
}
const ACTION_TEXT = { decide: '승인 결정', request_changes: '수정 요청', pause: '일시 중지', resume: '재개', cancel: '실행 취소' } as const

const state = computed(() => (props.snapshot ? RUN_STATE[props.snapshot.state] : null))
const canControl = computed(() => !!props.snapshot && !props.isReplay && acceptsCommands(props.snapshot.state))
const canResume = computed(() => canControl.value && RESUMABLE_STATES.has(props.snapshot!.state))
const canPause = computed(() => canControl.value && !['paused', 'failed'].includes(props.snapshot!.state))
const busy = computed(() => props.pending !== null)
</script>

<template>
  <header class="run-header">
    <div class="id">
      <button type="button" class="btn small" @click="emit('home')">← 처음</button>
      <div>
        <h1>개발 사무실</h1>
        <p class="small muted">
          프로젝트 <code :title="snapshot?.project_id">{{ shortId(snapshot?.project_id) }}</code>
          · 실행 <code :title="snapshot?.run_id">{{ shortId(snapshot?.run_id) }}</code>
          · 명세 <code :title="snapshot?.spec_version_id ?? undefined">{{ snapshot?.spec_version_id ? shortId(snapshot.spec_version_id) : '미확정' }}</code>
        </p>
      </div>
    </div>

    <div class="status">
      <SourceBadge :kind="kind" :snapshot="snapshot" />
      <span v-if="state" :class="['tone', `tone-${state.tone}`]" aria-label="실행 상태">
        <span aria-hidden="true">{{ state.glyph }}</span> {{ state.text }}
      </span>
      <span :class="['chip', `tone-${CONNECTION[connection].tone}`]" aria-label="연결 상태">
        {{ CONNECTION[connection].text }}
      </span>
      <button v-if="connection === 'closed' && snapshot" type="button" class="btn small" @click="emit('reconnect')">다시 연결</button>
      <span v-if="pending" class="chip tone-active" role="status">
        {{ ACTION_TEXT[pending.action] }} {{ pending.receipt ? '접수됨 · 반영 확인 중' : '보내는 중' }}
      </span>
    </div>

    <div class="controls">
      <ThemeControls :motion="motion" @update:motion="emit('update:motion', $event)" />
      <template v-if="canControl">
        <button v-if="canResume" type="button" class="btn" :disabled="busy" @click="emit('resume')">▶ 재개</button>
        <button v-if="canPause" type="button" class="btn" :disabled="busy" @click="emit('pause')">❙❙ 일시 중지</button>
        <button type="button" class="btn danger" :disabled="busy" @click="emit('cancel')">■ 실행 취소</button>
      </template>
      <span v-else-if="isReplay" class="small muted">재생은 읽기 전용</span>
    </div>
  </header>
</template>

<style scoped>
.run-header {
  position: sticky; top: 0; z-index: 5;
  display: grid; grid-template-columns: auto 1fr auto; gap: 8px 16px; align-items: center;
  padding: 10px 16px; background: var(--surface); border-bottom: 1px solid var(--line);
}
.id { display: flex; align-items: center; gap: 12px; min-width: 0; }
h1 { font-size: 1.1rem; }
.status { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; min-width: 0; }
.id > div { min-width: 0; }
.controls { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; justify-content: flex-end; }
@media (max-width: 1100px) {
  .run-header { grid-template-columns: 1fr auto; }
  .status { grid-column: 1 / -1; grid-row: 2; }
}
@media (max-width: 640px) {
  .run-header { grid-template-columns: 1fr; position: static; }
  .controls { justify-content: flex-start; }
}
</style>
