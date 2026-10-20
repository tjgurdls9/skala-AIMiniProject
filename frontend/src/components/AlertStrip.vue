<script setup lang="ts">
import type { Alert, AlertAction } from '../model/alerts'

defineProps<{ alerts: Alert[]; notices: string[] }>()
const emit = defineEmits<{ act: [action: AlertAction] }>()

const ACTION_TEXT: Record<AlertAction['kind'], string> = { plan: '기획 검토', release: '배포 대상 검토', preview: '프리뷰 보기', task: '작업 보기' }
</script>

<template>
  <section v-if="alerts.length || notices.length" class="alerts" aria-label="고정 알림 (관련도와 무관하게 항상 표시)">
    <ul class="plain">
      <li v-for="a in alerts" :key="a.key" :class="['alert', `tone-${a.tone}`]">
        <span class="glyph" aria-hidden="true">{{ a.glyph }}</span>
        <span class="text">{{ a.text }}</span>
        <button v-if="a.action" type="button" class="btn small" @click="emit('act', a.action)">{{ ACTION_TEXT[a.action.kind] }}</button>
      </li>
      <li v-for="(n, i) in notices" :key="`n${i}`" class="alert tone-neutral">
        <span class="glyph" aria-hidden="true">ℹ</span>
        <span class="text">{{ n }}</span>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.alerts { padding: 8px 16px 0; }
.alert {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  padding: 6px 10px; margin-bottom: 6px; border: 1px solid currentColor; border-left-width: 4px;
  border-radius: var(--radius); background: var(--surface); font-weight: 600;
}
.alert .text { flex: 1 1 260px; color: var(--ink); font-weight: 500; }
.glyph { font-weight: 700; }
</style>
