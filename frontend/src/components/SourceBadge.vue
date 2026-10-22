<script setup lang="ts">
import { computed } from 'vue'
import type { SourceKind } from '../api/source'
import type { Snapshot } from '../api/types'
import { formatTime, shortDigest, shortId } from '../model/labels'

/** LIVE 배지는 연결 출처가 실제 API이고 snapshot.mode가 live일 때만 붙인다. 예시의 mode 값만 보고 붙이지 않는다. */
const props = defineProps<{ kind: SourceKind; snapshot: Snapshot | null; demoBadge?: string }>()

const badge = computed(() => {
  if (props.kind === 'example') return { cls: 'example', text: props.demoBadge ?? '합성 예시 · 실제 실행 아님' }
  if (props.snapshot?.mode === 'replay' && props.snapshot.replay_source?.provenance === 'imported_unsigned') {
    return { cls: 'imported', text: '가져온 기록(서명 없음) · 읽기 전용' }
  }
  if (props.snapshot?.mode === 'replay') return { cls: 'replay', text: '실제 기록 재생 · 읽기 전용' }
  if (props.snapshot?.mode === 'live') return { cls: 'live', text: 'LIVE' }
  return { cls: 'unknown', text: '연결 확인 중' }
})
const replay = computed(() => (props.kind === 'live' ? props.snapshot?.replay_source : undefined))
</script>

<template>
  <span :class="['source', badge.cls]">
    <strong>{{ badge.text }}</strong>
    <span v-if="replay" class="small">
      원본 실행 <code :title="replay.source_run_id">{{ shortId(replay.source_run_id) }}</code> · 기록 {{ formatTime(replay.recorded_at) }} · manifest <code>{{ shortDigest(replay.manifest_digest) }}</code>
      <template v-if="replay.provenance === 'imported_unsigned'"> · 해시는 훼손 검출용이며 출처 서명이 아님</template>
    </span>
  </span>
</template>

<style scoped>
.source { display: inline-flex; flex-wrap: wrap; max-width: 100%; align-items: center; gap: 4px 8px; padding: 4px 10px; border-radius: 6px; border: 1px solid currentColor; }
.example { color: var(--example); background: var(--example-bg); }
.replay { color: var(--replay); background: var(--replay-bg); }
.imported { color: var(--tone-wait); background: var(--surface-2); border-style: dashed; }
.live { color: var(--live); background: var(--live-bg); }
.unknown { color: var(--ink-3); }
</style>
