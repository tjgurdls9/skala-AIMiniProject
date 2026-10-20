<script setup lang="ts">
import { ref, watch } from 'vue'
import type { Snapshot } from '../api/types'
import type { SendResult } from '../composables/useCommandForm'
import type { CommandInput } from '../composables/useRun'
import { RUN_STATE } from '../model/labels'
import BaseDialog from './BaseDialog.vue'
import ChangeRequestForm from './ChangeRequestForm.vue'

/**
 * 입력 필요·실패 상태에서 기존 request_changes 명령으로 원문을 보태 재기획을 요청한다.
 * 새 명령을 만들지 않으며, 범위 판단과 재승인 요구는 서버가 한다.
 */
const props = defineProps<{
  open: boolean
  snapshot: Snapshot
  send: (input: CommandInput, commandId: string) => Promise<SendResult>
}>()
const emit = defineEmits<{ close: [] }>()
const sent = ref(false)
watch(() => props.open, (open) => {
  if (open) sent.value = false
})
</script>

<template>
  <BaseDialog :open="open" title="수정 요청으로 다시 기획" :subtitle="`현재 상태: ${RUN_STATE[snapshot.state].text}`" @close="emit('close')">
    <p v-if="snapshot.reason" class="info-box"><strong>서버가 알린 이유</strong> — {{ snapshot.reason }}</p>
    <p class="small muted">
      요청 원문은 서버 원장에 그대로 보존됩니다. 필수 조건을 줄이거나 나누려면 무엇을 바꿀지 적어 주세요.
      재기획 뒤에는 기획 승인이 다시 필요합니다.
    </p>
    <p v-if="sent" class="info-box" role="status">수정 요청이 접수됐습니다. 반영 여부는 실행 상태와 사건 기록으로 확인하세요.</p>
    <ChangeRequestForm
      v-else
      :run-id="snapshot.run_id"
      :artifact-ids="[]"
      :artifact-titles="{}"
      :disabled="false"
      default-scope="spec"
      :send="send"
      @sent="sent = true"
    />
    <template #foot>
      <button type="button" class="btn" @click="emit('close')">닫기</button>
    </template>
  </BaseDialog>
</template>
