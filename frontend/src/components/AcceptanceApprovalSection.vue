<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { RunSource } from '../api/source'
import type { Snapshot } from '../api/types'
import type { SendResult } from '../composables/useCommandForm'
import { useCommandForm } from '../composables/useCommandForm'
import { useDraft } from '../composables/useDraft'
import type { CommandInput } from '../composables/useRun'
import { acceptanceApprovals, acceptanceMismatch, currentAcceptance, MANUAL_STATE, manualPendingOf, type ManualState } from '../model/acceptanceApproval'
import { reviewPair } from '../model/derive'
import { shortDigest } from '../model/labels'
import CommandFeedback from './CommandFeedback.vue'

/**
 * CR-C18 사람 확인 필요 AC. 정확한 후보(커밋·이미지)·AC id·검증 보고서에 묶인 대상을 승인하거나 거절한다.
 * 승인은 사람 확인 AC의 자동 판정을 바꾸지 않는다(미실행 그대로). 최종 검사는 서버가 한다.
 */
const props = defineProps<{ snapshot: Snapshot; source: RunSource; readOnly: boolean; send: (input: CommandInput, commandId: string) => Promise<SendResult> }>()
const emit = defineEmits<{ artifact: [id: string] }>()

const { text: feedback, clear } = useDraft(`draft:${props.snapshot.run_id}:acceptance-feedback`)
const form = useCommandForm()

const current = computed(() => currentAcceptance(props.snapshot))
const pair = computed(() => reviewPair(props.snapshot))
const mismatch = computed(() => (current.value ? acceptanceMismatch(current.value.target, pair.value) : null))
const invalidated = computed(() => acceptanceApprovals(props.snapshot).filter((a) => a.state === 'invalidated').length)
const label = computed(() => (current.value ? MANUAL_STATE[current.value.state as ManualState] : null))
const validatorPassed = computed(() => pair.value.validator?.verdict === 'pass')

// 검증 보고서 본문의 manual_pending. 읽지 못하면 표시하지 않는다(승인 대상의 AC 목록이 기준)
const reported = ref<string[] | null>(null)
let token = 0
watch(
  () => [current.value?.id, pair.value.validator?.artifact_id] as const,
  async ([id, artifactId]) => {
    const mine = ++token
    reported.value = null
    if (!id || !artifactId) return
    try {
      const body = await props.source.getArtifact(artifactId)
      if (mine === token) reported.value = manualPendingOf(body)
    } catch {
      // 본문을 읽지 못해도 승인 대상의 AC 목록으로 결정할 수 있다
    }
  },
  { immediate: true },
)
const reportDiffers = computed(() => {
  const target = current.value?.target.ac_ids
  return !!target && !!reported.value && (reported.value.length !== target.length || reported.value.some((id) => !target.includes(id)))
})

watch(() => [current.value?.id, current.value?.target_digest], () => form.renew({ keepError: true }))

async function decide(decision: 'approve' | 'reject'): Promise<void> {
  const approval = current.value
  if (!approval || approval.state !== 'pending') return
  const text = feedback.value.trim()
  const ok = await form.run((commandId) =>
    props.send({ action: 'decide', payload: { approval_id: approval.id, target_digest: approval.target_digest, decision, ...(text ? { feedback: text } : {}) } }, commandId),
  )
  if (ok) clear()
}
</script>

<template>
  <section v-if="current && label" class="manual" aria-label="사람 확인 필요">
    <h3>사람 확인 필요</h3>
    <p :class="['tone', `tone-${label.tone}`]">{{ label.glyph }} {{ label.text }}</p>
    <p class="small muted">
      자동 점검 없이 사람이 확인하기로 한 AC입니다. 승인해도 이 AC의 자동 판정은 '미실행' 그대로이며 '충족'으로 바뀌지 않습니다.
    </p>
    <p v-if="invalidated" class="info-box small">이전 사람 확인 승인 {{ invalidated }}건은 무효화됐습니다. 아래가 현재 대상입니다.</p>
    <dl class="kv small">
      <dt>후보 커밋</dt><dd><code>{{ current.target.commit_sha }}</code></dd>
      <dt>이미지 digest</dt><dd><code>{{ current.target.image_digest }}</code></dd>
      <dt>확인할 AC</dt><dd><code v-for="id in current.target.ac_ids" :key="id" class="id">{{ id }}</code></dd>
      <dt>검증 보고서</dt>
      <dd>
        <code>{{ current.target.validator_report_id }}</code> · <code>{{ shortDigest(current.target.validator_report_digest) }}</code>
        <button v-if="pair.validator" type="button" class="btn small" @click="emit('artifact', pair.validator.artifact_id)">원본 보고서 보기</button>
      </dd>
      <dt>승인 대상 해시</dt><dd><code>{{ shortDigest(current.target_digest) }}</code> <span class="muted">(서버 제공 · 그대로 전송)</span></dd>
    </dl>
    <p v-if="validatorPassed" class="small muted">
      검증 보고서의 '통과'는 사람 확인을 제외한 AC가 승인된 점검으로 충족됐다는 뜻입니다. 사람 확인 AC는 포함하지 않습니다.
    </p>
    <p v-if="reported" class="small">보고서가 사람 확인 대기로 표시한 AC: <code v-for="id in reported" :key="id" class="id">{{ id }}</code><template v-if="!reported.length"> 없음</template></p>
    <p v-if="reportDiffers" class="error-box small" role="alert">승인 대상 AC와 보고서가 표시한 AC가 다릅니다. 서버 대상을 확인한 뒤 결정하세요.</p>
    <p v-if="mismatch" class="error-box" role="alert">{{ mismatch }} 이 대상은 승인할 수 없습니다.</p>

    <template v-if="current.state === 'pending'">
      <p v-if="readOnly" class="info-box">실제 기록 재생은 읽기 전용입니다. 내용만 확인할 수 있습니다.</p>
      <template v-else>
        <label class="field">
          의견 (거절 시 필수)
          <textarea v-model="feedback" maxlength="8000" />
        </label>
        <CommandFeedback :error="form.error.value" />
        <div class="actions">
          <button type="button" class="btn danger reject" :disabled="form.submitting.value || !feedback.trim()" @click="decide('reject')">사람 확인 거절</button>
          <button type="button" class="btn primary approve" :disabled="form.submitting.value || !!mismatch" @click="decide('approve')">
            {{ form.submitting.value ? '보내는 중…' : '이 AC를 사람이 확인함 · 승인' }}
          </button>
        </div>
      </template>
    </template>
    <p v-else-if="current.feedback" class="small">의견: {{ current.feedback }}</p>
  </section>
</template>

<style scoped>
.manual { display: grid; gap: 8px; border: 1px solid var(--line); border-radius: var(--radius); padding: 12px; }
h3 { font-size: 0.9rem; color: var(--ink-3); }
.id + .id { margin-left: 6px; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; }
</style>
