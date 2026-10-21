<script setup lang="ts">
import { computed } from 'vue'
import type { AcceptanceItem, ReviewReport } from '../api/types'
import { AC_STATE, acView } from '../model/acceptance'
import { MANUAL_STATE, type ManualState } from '../model/acceptanceApproval'

/**
 * AC별 서버 판정(CR-C09). 작업 완료 수와 섞지 않는다. 근거는 판정이 가리킨 원본 보고서로 연결한다.
 * 보안 실패는 별도 보고서·알림으로 보이며 여기의 기능 AC 충족과 합치지 않는다.
 * 사람 확인 AC(CR-C18)는 판정을 그대로 두고 승인 상태를 따로 덧붙인다. 승인됐다고 충족으로 바꾸지 않는다.
 */
const props = defineProps<{
  ids: readonly string[]
  index: ReadonlyMap<string, AcceptanceItem>
  reports: readonly ReviewReport[]
  manual?: ReadonlyMap<string, ManualState>
}>()
const emit = defineEmits<{ artifact: [id: string] }>()

const reportIds = computed(() => new Set(props.reports.map((r) => r.id)))
const rows = computed(() =>
  props.ids.map((id) => {
    const view = acView(props.index, id, reportIds.value)
    const report = view.reportId ? props.reports.find((r) => r.id === view.reportId) : undefined
    const manual = props.manual?.get(id)
    return { id, ...view, label: AC_STATE[view.state], report, manual: manual ? MANUAL_STATE[manual] : null }
  }),
)
</script>

<template>
  <ul class="plain ac-list">
    <li v-for="row in rows" :key="row.id" class="ac">
      <code>{{ row.id }}</code>
      <span :class="['tone', `tone-${row.label.tone}`]">{{ row.label.glyph }} {{ row.label.text }}</span>
      <span v-if="row.manual" :class="['tone', 'manual-state', `tone-${row.manual.tone}`]" title="사람이 확인한 기록입니다. 자동 판정이 아닙니다.">{{ row.manual.glyph }} {{ row.manual.text }}</span>
      <button
        v-if="row.report"
        type="button"
        class="link small"
        @click="emit('artifact', row.report.artifact_id)"
      >근거: {{ row.report.role === 'validator' ? '검증' : '보안' }} 보고서</button>
      <span v-else-if="row.state === 'stale'" class="small muted">현재 회차에 근거 보고서가 없어 충족으로 보지 않음</span>
    </li>
  </ul>
</template>

<style scoped>
.ac-list { display: grid; gap: 2px; }
.ac { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 10px; min-height: 32px; }
.link { border: 0; background: none; color: var(--focus); text-decoration: underline; text-underline-offset: 3px; cursor: pointer; min-height: 32px; padding: 0; }
</style>
