<script setup lang="ts">
import { ref, watch } from 'vue'
import { ApiError } from '../api/errors'
import type { RunSource } from '../api/source'
import type { Approval, PlanTarget, PlanView } from '../api/types'
import type { SendResult } from '../composables/useCommandForm'
import { useCommandForm } from '../composables/useCommandForm'
import { useDraft } from '../composables/useDraft'
import type { CommandInput } from '../composables/useRun'
import { shortDigest } from '../model/labels'
import BaseDialog from './BaseDialog.vue'
import CommandFeedback from './CommandFeedback.vue'
import PlanViewBody from './PlanViewBody.vue'

/**
 * 기획 승인: 서버가 제시한 승인 대상(approval_id·target_digest)을 그대로 보낸다. 클라이언트가 해시를 만들지 않는다.
 * 승인 = "이 기획으로 구현 시작", 거절 = 의견을 달아 수정 요청.
 */
const props = defineProps<{
  open: boolean
  approval: (Approval & { target: PlanTarget }) | null
  specArtifactId: string | null
  source: RunSource
  runId: string
  send: (input: CommandInput, commandId: string) => Promise<SendResult>
}>()
const emit = defineEmits<{ close: [] }>()

const plan = ref<PlanView | null>(null)
const planError = ref<string | null>(null)
const { text: feedback, clear } = useDraft(`draft:${props.runId}:plan-feedback`)
const form = useCommandForm()

watch(
  () => [props.open, props.specArtifactId] as const,
  async ([open, id]) => {
    if (!open) return
    form.reset()
    plan.value = null
    planError.value = null
    if (!id) {
      planError.value = '기획 아티팩트가 스냅샷에 없습니다.'
      return
    }
    try {
      plan.value = (await props.source.getArtifact(id)) as PlanView
    } catch (error) {
      planError.value = error instanceof ApiError ? error.message : '기획 본문을 읽지 못했습니다.'
    }
  },
  { immediate: true },
)

async function decide(decision: 'approve' | 'reject'): Promise<void> {
  const approval = props.approval
  if (!approval) return
  const text = feedback.value.trim()
  const ok = await form.run((commandId) =>
    props.send(
      {
        action: 'decide',
        payload: { approval_id: approval.id, target_digest: approval.target_digest, decision, ...(text ? { feedback: text } : {}) },
      },
      commandId,
    ),
  )
  if (ok) {
    clear()
    emit('close')
  }
}
</script>

<template>
  <BaseDialog :open="open" title="기획 승인" subtitle="승인하면 이 버전의 명세로 구현을 시작합니다. 승인 전에는 구현·외부 작업이 실행되지 않습니다." @close="emit('close')">
    <p v-if="!approval" class="info-box">대기 중인 기획 승인이 없습니다. 이미 결정됐거나 대상이 바뀌었을 수 있습니다.</p>
    <template v-else>
      <dl class="kv small">
        <dt>명세 버전</dt><dd><code>{{ approval.target.spec_version_id }}</code></dd>
        <dt>기획 해시</dt><dd><code>{{ shortDigest(approval.target.plan_digest) }}</code></dd>
        <dt>승인 대상 해시</dt><dd><code>{{ shortDigest(approval.target_digest) }}</code> <span class="muted">(서버 제공 · 그대로 전송)</span></dd>
      </dl>
      <p v-if="planError" class="error-box">{{ planError }} 본문 없이 승인하지 마세요.</p>
      <p v-else-if="!plan" class="muted">기획 본문 읽는 중…</p>
      <template v-else>
        <p v-if="plan.spec_version_id !== approval.target.spec_version_id" class="error-box" role="alert">
          표시 중인 기획({{ plan.spec_version_id }})과 승인 대상({{ approval.target.spec_version_id }})의 버전이 다릅니다. 최신 대상을 다시 여세요.
        </p>
        <PlanViewBody :plan="plan" />
      </template>
      <label class="field">
        의견
        <span class="hint small muted">거절할 때는 무엇을 고칠지 적어 주세요. 입력은 재접속해도 보존됩니다.</span>
        <textarea v-model="feedback" maxlength="8000" />
      </label>
      <CommandFeedback :error="form.error.value" />
    </template>

    <template #foot>
      <button type="button" class="btn" @click="emit('close')">닫기</button>
      <template v-if="approval">
        <button type="button" class="btn danger" :disabled="form.submitting.value || !feedback.trim()" @click="decide('reject')">
          수정 요청(거절)
        </button>
        <button
          type="button"
          class="btn primary"
          :disabled="form.submitting.value || !plan || plan.spec_version_id !== approval.target.spec_version_id"
          @click="decide('approve')"
        >
          {{ form.submitting.value ? '보내는 중…' : '이 기획으로 구현 시작' }}
        </button>
      </template>
    </template>
  </BaseDialog>
</template>
