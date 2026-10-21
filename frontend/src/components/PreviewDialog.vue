<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ApiError } from '../api/errors'
import type { RunSource } from '../api/source'
import type { Preview, Snapshot } from '../api/types'
import type { SendResult } from '../composables/useCommandForm'
import type { CommandInput } from '../composables/useRun'
import { reviewPair } from '../model/derive'
import { shortDigest } from '../model/labels'
import AcceptanceApprovalSection from './AcceptanceApprovalSection.vue'
import BaseDialog from './BaseDialog.vue'
import ChangeRequestForm from './ChangeRequestForm.vue'
import PreviewFrame from './PreviewFrame.vue'
import ReviewPair from './ReviewPair.vue'

/** 프리뷰: 후보 커밋·두 검토 결과·근거를 보고 구현 수정 또는 기획 변경을 요청한다. */
const props = defineProps<{
  open: boolean
  snapshot: Snapshot
  source: RunSource
  readOnly: boolean
  selectedArtifactId: string | null
  send: (input: CommandInput, commandId: string) => Promise<SendResult>
}>()
const emit = defineEmits<{ close: []; artifact: [id: string] }>()

const pair = computed(() => reviewPair(props.snapshot))
const previewArtifact = computed(() => [...props.snapshot.artifacts].reverse().find((a) => a.kind === 'preview') ?? null)
const titles = computed(() => Object.fromEntries(props.snapshot.artifacts.map((a) => [a.id, a.title])))
const attachIds = computed(() => [props.selectedArtifactId, previewArtifact.value?.id].filter((id, i, arr): id is string => !!id && arr.indexOf(id) === i))
const preview = ref<unknown>(null)
const currentCommit = computed(() => pair.value.validator?.commit_sha ?? pair.value.security?.commit_sha ?? null)
/** CODEX-UI-001: 실행 중인 현재 후보의 프리뷰일 때만 iframe을 연다 */
const recordReason = computed<string | null>(() => {
  if (props.source.kind === 'example') return '합성 예시입니다.'
  if (props.snapshot.replay_source?.provenance === 'imported_unsigned') return '가져온 기록(서명 없음)에서는 외부 앱을 열지 않습니다.'
  if (props.readOnly) return '실제 기록 재생에서는 외부 앱을 열지 않습니다.'
  if (props.snapshot.state !== 'preview_ready') return '현재 프리뷰 확인 단계가 아니어서 과거 기록으로만 표시합니다.'
  const commit = (preview.value as Partial<Preview> | null)?.commit_sha
  if (commit && currentCommit.value && commit !== currentCommit.value) return '현재 후보와 다른 옛 후보의 프리뷰입니다.'
  return null
})
const previewError = ref<string | null>(null)
const sent = ref(false)

watch(
  () => [props.open, previewArtifact.value?.id] as const,
  async ([open, id]) => {
    if (!open) return
    sent.value = false
    preview.value = null
    previewError.value = null
    if (!id) return
    try {
      const body = await props.source.getArtifact(id)
      if (previewArtifact.value?.id === id) preview.value = body
    } catch (error) {
      if (previewArtifact.value?.id === id) previewError.value = error instanceof ApiError && error.code !== 'NOT_FOUND' ? `프리뷰 정보를 읽지 못했습니다: ${error.message}` : null
    }
  },
  { immediate: true },
)
</script>

<template>
  <BaseDialog :open="open" title="프리뷰 확인" subtitle="두 검토 결과와 프리뷰를 보고 사람 확인과 수정 방향을 정합니다." @close="emit('close')">
    <section>
      <h3>후보</h3>
      <dl class="kv small">
        <dt>커밋</dt><dd><code>{{ shortDigest(pair.validator?.commit_sha ?? pair.security?.commit_sha) }}</code></dd>
        <dt>이미지</dt><dd><code>{{ shortDigest(pair.validator?.image_digest ?? pair.security?.image_digest) }}</code></dd>
        <dt>프리뷰 아티팩트</dt><dd>{{ previewArtifact ? previewArtifact.public_summary : '없음' }}</dd>
      </dl>
    </section>
    <p v-if="previewError" class="error-box" role="alert">{{ previewError }}</p>
    <PreviewFrame v-else :preview="preview" :record-reason="recordReason" />
    <section>
      <h3>독립 검토</h3>
      <ReviewPair :pair="pair" @artifact="emit('artifact', $event)" />
    </section>
    <AcceptanceApprovalSection :snapshot="snapshot" :source="source" :read-only="readOnly" :send="send" @artifact="emit('artifact', $event)" />
    <section>
      <h3>수정 요청</h3>
      <p v-if="readOnly" class="info-box">실제 기록 재생은 읽기 전용입니다. 수정하려면 새 LIVE 실행을 만드세요.</p>
      <p v-else-if="sent" class="info-box" role="status">수정 요청이 접수됐습니다. 반영 여부는 사건 기록과 실행 상태로 확인하세요.</p>
      <ChangeRequestForm
        v-else
        :run-id="snapshot.run_id"
        :artifact-ids="attachIds"
        :artifact-titles="titles"
        :disabled="readOnly"
        :send="send"
        @sent="sent = true"
      />
    </section>
    <template #foot>
      <button type="button" class="btn" @click="emit('close')">닫기</button>
    </template>
  </BaseDialog>
</template>

<style scoped>
h3 { font-size: 0.9rem; color: var(--ink-3); margin-bottom: 6px; }
</style>
