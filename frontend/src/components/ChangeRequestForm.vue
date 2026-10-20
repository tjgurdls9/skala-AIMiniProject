<script setup lang="ts">
import { ref } from 'vue'
import type { SendResult } from '../composables/useCommandForm'
import { useCommandForm } from '../composables/useCommandForm'
import { useDraft } from '../composables/useDraft'
import type { CommandInput } from '../composables/useRun'
import CommandFeedback from './CommandFeedback.vue'

/**
 * 수정 요청: 기존 범위 안의 구현 수정과 범위를 바꾸는 기획 변경을 구분한다.
 * 실제 범위 판정은 서버가 한다(구현으로 보내도 기획 재승인을 요구할 수 있음).
 */
const props = defineProps<{
  runId: string
  artifactIds: string[]
  artifactTitles: Record<string, string>
  disabled: boolean
  defaultScope?: 'implementation' | 'spec'
  send: (input: CommandInput, commandId: string) => Promise<SendResult>
}>()
const emit = defineEmits<{ sent: [] }>()

const scope = ref<'implementation' | 'spec'>(props.defaultScope ?? 'implementation')
const { text: feedback, clear } = useDraft(`draft:${props.runId}:change-feedback`)
const attach = ref(true)
const form = useCommandForm()

async function submit(): Promise<void> {
  const text = feedback.value.trim()
  if (!text) return
  const ids = attach.value ? props.artifactIds : []
  const ok = await form.run((commandId) =>
    props.send({ action: 'request_changes', payload: { scope: scope.value, feedback: text, ...(ids.length ? { artifact_ids: ids } : {}) } }, commandId),
  )
  if (ok) {
    clear()
    emit('sent')
  }
}
</script>

<template>
  <form class="change" @submit.prevent="submit">
    <fieldset>
      <legend>수정 범위</legend>
      <label class="option">
        <input v-model="scope" type="radio" value="implementation" />
        <span><strong>구현 수정</strong> — 승인된 범위 안에서 결과를 고침 (구현 Sprint로 돌아감)</span>
      </label>
      <label class="option">
        <input v-model="scope" type="radio" value="spec" />
        <span><strong>기획 변경</strong> — 기능·스택·데이터·배포 대상이 바뀜 (기획 재승인 필요)</span>
      </label>
    </fieldset>
    <label class="field">
      무엇을 바꿀까요?
      <span class="hint small muted">입력은 재접속·새로고침해도 보존됩니다.</span>
      <textarea v-model="feedback" maxlength="8000" required />
    </label>
    <label v-if="artifactIds.length" class="small option">
      <input v-model="attach" type="checkbox" />
      <span>근거로 첨부: {{ artifactIds.map((id) => artifactTitles[id] ?? id).join(', ') }}</span>
    </label>
    <p class="small muted">서버가 실제 범위를 판단합니다. 구현 수정으로 보내도 범위 변경이면 기획 재승인을 요구할 수 있습니다.</p>
    <CommandFeedback :error="form.error.value" />
    <button type="submit" class="btn primary" :disabled="disabled || form.submitting.value || !feedback.trim()">
      {{ form.submitting.value ? '보내는 중…' : '수정 요청 보내기' }}
    </button>
  </form>
</template>

<style scoped>
.change { display: grid; gap: 12px; }
fieldset { border: 1px solid var(--line); border-radius: var(--radius); padding: 8px 12px; display: grid; gap: 4px; }
legend { font-weight: 600; padding: 0 4px; }
.option { display: flex; gap: 8px; align-items: flex-start; min-height: var(--tap); padding-top: 8px; }
.option input { margin-top: 4px; }
button[type="submit"] { justify-self: end; }
</style>
