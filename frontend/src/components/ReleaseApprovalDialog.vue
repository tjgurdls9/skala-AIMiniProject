<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ApiError } from '../api/errors'
import type { RunSource } from '../api/source'
import type { Approval, Environment, ReleaseTarget, Snapshot } from '../api/types'
import type { SendResult } from '../composables/useCommandForm'
import { useCommandForm } from '../composables/useCommandForm'
import { useDraft } from '../composables/useDraft'
import type { CommandInput } from '../composables/useRun'
import { MANUAL_STATE, releaseAcceptanceGate } from '../model/acceptanceApproval'
import { bothPassed, reviewPair } from '../model/derive'
import { shortDigest } from '../model/labels'
import BaseDialog from './BaseDialog.vue'
import CommandFeedback from './CommandFeedback.vue'
import ReviewPair from './ReviewPair.vue'

/**
 * 배포 승인: 커밋·이미지 digest·환경·두 보고서·복구 계획이 묶인 서버 대상을 그대로 승인한다.
 * 화면은 안전을 보장하지 않는다. 최종 검사는 서버가 한다.
 */
const props = defineProps<{
  open: boolean
  approval: (Approval & { target: ReleaseTarget }) | null
  snapshot: Snapshot
  source: RunSource
  readOnly: boolean
  /** CR-C15 ReleaseView.enabled. 계약상 현재 false 고정이며, false면 승인·거절을 보내지 않는다 */
  releaseEnabled: boolean
  send: (input: CommandInput, commandId: string) => Promise<SendResult>
}>()
const emit = defineEmits<{ close: []; artifact: [id: string] }>()

const env = ref<Environment | null>(null)
const envError = ref<string | null>(null)
const { text: feedback, clear } = useDraft(`draft:${props.snapshot.run_id}:release-feedback`)
const form = useCommandForm()

const pair = computed(() => (props.approval ? reviewPair(props.snapshot, props.approval.target.review_report_ids) : reviewPair(props.snapshot)))
const passed = computed(() => bothPassed(pair.value))
const matchesCandidate = computed(() => {
  const t = props.approval?.target
  return !!t && [pair.value.validator, pair.value.security].every((r) => r && r.commit_sha === t.commit_sha && r.image_digest === t.image_digest)
})
/** CR-C18 사람 확인 승인과의 결속. none이면(사람 확인 기록 없음·옛 기록) 구역을 그리지 않는다. 최종 검사는 서버가 한다 */
const manualGate = computed(() => (props.approval ? releaseAcceptanceGate(props.snapshot, props.approval.target) : { kind: 'none' as const }))
const manualBlocked = computed(() => manualGate.value.kind === 'blocked')
const invalidated = computed(() => props.snapshot.approvals.filter((a) => a.target.gate === 'release' && a.state === 'invalidated').length)

watch(
  () => [props.open, props.approval?.id, props.approval?.target_digest] as const,
  async ([open], prev) => {
    if (!open) return
    // 새로 열면 새 결정, 열린 채 대상이 바뀌면(409 뒤 재조회) 안내는 남기고 ID만 새로
    form.renew({ keepError: prev?.[0] === true })
    const id = props.approval?.target.environment_id
    env.value = null
    envError.value = null
    if (!id) return
    try {
      env.value = await props.source.getEnvironment(id)
    } catch (error) {
      envError.value = error instanceof ApiError && error.code === 'NOT_FOUND' ? '서버가 이 환경 정보를 제공하지 않습니다(미설정).' : '환경 정보를 읽지 못했습니다.'
    }
  },
  { immediate: true },
)

async function decide(decision: 'approve' | 'reject'): Promise<void> {
  const approval = props.approval
  if (!approval) return
  const text = feedback.value.trim()
  const ok = await form.run((commandId) =>
    props.send({ action: 'decide', payload: { approval_id: approval.id, target_digest: approval.target_digest, decision, ...(text ? { feedback: text } : {}) } }, commandId),
  )
  if (ok) {
    clear()
    emit('close')
  }
}
</script>

<template>
  <BaseDialog :open="open" title="배포 승인" subtitle="아래에 고정된 결과만 이 환경에 배포됩니다. 대상이 바뀌면 이 승인은 무효가 됩니다." @close="emit('close')">
    <p v-if="!approval" class="info-box">대기 중인 배포 승인이 없습니다. 이미 결정됐거나 대상이 바뀌었을 수 있습니다.</p>
    <template v-else>
      <p v-if="invalidated" class="info-box small">이전 배포 대상 {{ invalidated }}건은 무효화됐습니다. 아래가 현재 대상입니다.</p>
      <section>
        <h3>배포 환경</h3>
        <p v-if="env"><strong>{{ env.label }}</strong> · 노출 범위 <strong>{{ env.exposure }}</strong> · <code>{{ env.id }}</code></p>
        <p v-else-if="envError" class="tone tone-warn">{{ envError }} <code>{{ approval.target.environment_id }}</code></p>
        <p v-else class="muted">환경 정보 읽는 중…</p>
      </section>
      <dl class="kv small">
        <dt>커밋</dt><dd><code>{{ approval.target.commit_sha }}</code></dd>
        <dt>이미지 digest</dt><dd><code>{{ approval.target.image_digest }}</code></dd>
        <dt>명세 버전</dt><dd><code>{{ approval.target.spec_version_id }}</code></dd>
        <dt>환경 설정 해시</dt><dd><code>{{ shortDigest(approval.target.environment_config_digest) }}</code></dd>
        <dt>복구 계획 해시</dt><dd><code>{{ shortDigest(approval.target.rollback_manifest_digest) }}</code></dd>
        <dt>승인 대상 해시</dt><dd><code>{{ shortDigest(approval.target_digest) }}</code> <span class="muted">(서버 제공 · 그대로 전송)</span></dd>
      </dl>
      <section v-if="manualGate.kind !== 'none'" aria-label="사람 확인 승인">
        <h3>사람 확인 승인</h3>
        <template v-if="manualGate.approval">
          <p :class="['tone', `tone-${MANUAL_STATE[manualGate.approval.state as 'pending' | 'approved' | 'rejected']?.tone ?? 'neutral'}`]">
            {{ MANUAL_STATE[manualGate.approval.state as 'pending' | 'approved' | 'rejected']?.text ?? '무효' }} · <code>{{ manualGate.approval.id }}</code>
          </p>
          <dl class="kv small">
            <dt>확인한 AC</dt><dd><code v-for="id in manualGate.approval.target.ac_ids" :key="id" class="id">{{ id }}</code></dd>
            <dt>연결</dt><dd>{{ approval.target.acceptance_approval_id ? '배포 대상이 이 승인에 연결됨' : '배포 대상에 연결되지 않음' }}</dd>
          </dl>
        </template>
        <p v-if="manualGate.kind === 'blocked'" class="error-box" role="alert">{{ manualGate.reason }} 사람 확인이 끝나기 전에는 배포를 승인할 수 없습니다.</p>
        <p v-else class="small muted">사람이 확인한 기록입니다. 자동 판정(AC 충족)을 대신하지 않습니다.</p>
      </section>
      <section>
        <h3>대상에 묶인 두 보고서</h3>
        <ReviewPair :pair="pair" @artifact="emit('artifact', $event)" />
        <p v-if="!passed" class="error-box" role="alert">두 검토가 모두 통과하지 않아 승인할 수 없습니다.</p>
        <p v-else-if="!matchesCandidate" class="error-box" role="alert">보고서가 검토한 커밋·이미지가 배포 대상과 다릅니다. 승인하지 마세요.</p>
      </section>
      <label class="field">
        의견 (거절 시 필수)
        <textarea v-model="feedback" maxlength="8000" />
      </label>
      <CommandFeedback :error="form.error.value" />
      <p v-if="readOnly" class="info-box">실제 기록 재생은 읽기 전용입니다. 내용만 확인할 수 있습니다.</p>
      <p v-else-if="!releaseEnabled" class="info-box">서버가 실제 출시 실행을 비활성으로 알립니다. 대상과 두 보고서만 확인할 수 있고 승인·거절을 보내지 않습니다.</p>
    </template>
    <template #foot>
      <button type="button" class="btn" @click="emit('close')">닫기</button>
      <template v-if="approval && !readOnly && releaseEnabled">
        <button type="button" class="btn danger" :disabled="form.submitting.value || !feedback.trim()" @click="decide('reject')">배포 거절</button>
        <button type="button" class="btn primary" :disabled="form.submitting.value || !passed || !matchesCandidate || manualBlocked" @click="decide('approve')">
          {{ form.submitting.value ? '보내는 중…' : `이 결과를 ${env?.label ?? approval.target.environment_id}에 배포 승인` }}
        </button>
      </template>
    </template>
  </BaseDialog>
</template>

<style scoped>
h3 { font-size: 0.9rem; color: var(--ink-3); margin-bottom: 6px; }
</style>
