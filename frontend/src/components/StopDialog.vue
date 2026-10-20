<script setup lang="ts">
import type { SendResult } from '../composables/useCommandForm'
import { watch } from 'vue'
import { useCommandForm } from '../composables/useCommandForm'
import type { CommandInput } from '../composables/useRun'
import BaseDialog from './BaseDialog.vue'
import CommandFeedback from './CommandFeedback.vue'

/** 재개와 실행 취소는 확인 후 보낸다. 일시 중지는 확인 없이 바로 보낸다(헤더). */
const props = defineProps<{
  open: boolean
  action: 'resume' | 'cancel' | null
  send: (input: CommandInput, commandId: string) => Promise<SendResult>
}>()
const emit = defineEmits<{ close: [] }>()
const form = useCommandForm()
watch(() => [props.open, props.action] as const, ([open]) => {
  if (open) form.renew()
}, { immediate: true })

const TEXT = {
  resume: {
    title: '실행 재개',
    body: '재개하면 서버가 최신 명세·무료 공급자 자격·후보·승인 상태를 다시 확인한 뒤 이어서 진행합니다. 확인에 실패하면 재개되지 않습니다.',
    confirm: '재개',
  },
  cancel: {
    title: '실행 취소',
    body: '실행을 끝내고 기록만 남깁니다. 일시 중지와 달리 이어서 진행할 수 없습니다. 이미 시작된 외부 작업이 있다면 결과가 확인될 때까지 표시됩니다.',
    confirm: '실행 취소',
  },
} as const

async function confirm(): Promise<void> {
  if (!props.action) return
  const action = props.action
  if (await form.run((commandId) => props.send({ action, payload: {} }, commandId))) emit('close')
}
</script>

<template>
  <BaseDialog :open="open && !!action" :title="action ? TEXT[action].title : ''" @close="emit('close')">
    <p v-if="action">{{ TEXT[action].body }}</p>
    <CommandFeedback :error="form.error.value" />
    <template #foot>
      <button type="button" class="btn" @click="emit('close')">닫기</button>
      <button v-if="action" type="button" :class="['btn', action === 'cancel' ? 'danger' : 'primary']" :disabled="form.submitting.value" @click="confirm">
        {{ form.submitting.value ? '보내는 중…' : TEXT[action].confirm }}
      </button>
    </template>
  </BaseDialog>
</template>
