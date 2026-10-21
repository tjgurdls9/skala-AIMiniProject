<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ApiError } from '../api/errors'
import type { RunSource } from '../api/source'
import type { Approval, PlanTarget, PlanView } from '../api/types'
import type { SendResult } from '../composables/useCommandForm'
import { useCommandForm } from '../composables/useCommandForm'
import { useDraft } from '../composables/useDraft'
import type { CommandInput } from '../composables/useRun'
import { shortDigest } from '../model/labels'
import { supportVerdict } from '../model/planSupport'
import { isPlanView } from '../model/planView'
import BaseDialog from './BaseDialog.vue'
import CommandFeedback from './CommandFeedback.vue'
import PlanSupportBody from './PlanSupportBody.vue'
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
  readOnly: boolean
  send: (input: CommandInput, commandId: string) => Promise<SendResult>
}>()
const emit = defineEmits<{ close: [] }>()

const plan = ref<PlanView | null>(null)
const planError = ref<string | null>(null)
const { text: feedback, clear } = useDraft(`draft:${props.runId}:plan-feedback`)
const form = useCommandForm()

const support = computed(() => (plan.value ? supportVerdict(plan.value) : null))
/** 승인 가능: 본문이 있고, 승인 대상과 같은 명세이며, 지원 정보가 다른 명세이거나 구현 불가로 표시되지 않았을 때 */
const canApprove = computed(() =>
  !!plan.value && plan.value.spec_version_id === props.approval?.target.spec_version_id
  && support.value?.kind !== 'mismatch' && support.value?.kind !== 'blocked')

async function loadPlan(id: string | null): Promise<void> {
  plan.value = null
  planError.value = null
  if (!id) {
    planError.value = '기획 아티팩트가 스냅샷에 없습니다.'
    return
  }
  try {
    const body = await props.source.getArtifact(id)
    if (props.specArtifactId !== id) return
    if (isPlanView(body)) plan.value = body
    else planError.value = '기획 본문 형식이 계약(PlanView)과 맞지 않습니다.'
  } catch (error) {
    planError.value = error instanceof ApiError ? error.message : '기획 본문을 읽지 못했습니다.'
  }
}

watch(
  () => [props.open, props.specArtifactId, props.approval?.id, props.approval?.target_digest] as const,
  async ([open, id], prev) => {
    if (!open) return
    // 새로 열면 새 결정, 열린 채 대상이 바뀌면(409 뒤 재조회) 안내는 남기고 ID만 새로
    form.renew({ keepError: prev?.[0] === true })
    await loadPlan(id)
  },
  { immediate: true },
)

/** 다른 대안으로 다시 기획: 승인이 아니라 수정 요청(request_changes, scope=spec, alternative_id)이다 */
async function chooseAlternative(alternativeId: string): Promise<void> {
  const target = plan.value?.alternatives?.find((a) => a.id === alternativeId)
  if (!target) return
  const text = feedback.value.trim()
  const note = text || `다른 대안 선택: ${target.summary}`
  const ok = await form.run((commandId) =>
    props.send({ action: 'request_changes', payload: { scope: 'spec', feedback: note, alternative_id: alternativeId } }, commandId),
  )
  if (ok) {
    clear()
    emit('close')
  }
}

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
        <PlanSupportBody v-if="support" :verdict="support" @reload="loadPlan(specArtifactId)" />
        <PlanViewBody :plan="plan" :show-support="false" :interactive="!readOnly" :busy="form.submitting.value" @choose="chooseAlternative" />
      </template>
      <label class="field">
        의견
        <span class="hint small muted">거절할 때는 무엇을 고칠지 적어 주세요. 입력은 재접속해도 보존됩니다.</span>
        <textarea v-model="feedback" maxlength="8000" />
      </label>
      <CommandFeedback :error="form.error.value" />
      <p v-if="readOnly" class="info-box">실제 기록 재생은 읽기 전용입니다. 내용만 확인할 수 있습니다.</p>
    </template>

    <template #foot>
      <button type="button" class="btn" @click="emit('close')">닫기</button>
      <template v-if="approval && !readOnly">
        <button type="button" class="btn danger" :disabled="form.submitting.value || !feedback.trim()" @click="decide('reject')">
          수정 요청(거절)
        </button>
        <button
          type="button"
          class="btn primary"
          :disabled="form.submitting.value || !canApprove"
          @click="decide('approve')"
        >
          {{ form.submitting.value ? '보내는 중…' : '이 기획으로 구현 시작' }}
        </button>
      </template>
    </template>
  </BaseDialog>
</template>
