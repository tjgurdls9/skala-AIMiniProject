<script setup lang="ts">
import { ref } from 'vue'
import { applyTheme, currentTheme, type ThemeChoice } from '../composables/theme'

/** 표시 옵션만 바꾼다. 실행·선택·입력 상태와 무관하다. 시각화 테마는 사무실 하나다. */
defineProps<{ motion: boolean }>()
const emit = defineEmits<{ 'update:motion': [value: boolean] }>()

const theme = ref<ThemeChoice>(currentTheme())
const NEXT: Record<ThemeChoice, ThemeChoice> = { system: 'light', light: 'dark', dark: 'system' }
const LABEL: Record<ThemeChoice, string> = { system: '시스템', light: '라이트', dark: '다크' }

function cycle(): void {
  theme.value = NEXT[theme.value]
  applyTheme(theme.value)
}
</script>

<template>
  <div class="theme-controls">
    <button type="button" class="btn icon" :title="`화면 밝기: ${LABEL[theme]}`" :aria-label="`화면 밝기: ${LABEL[theme]}. 눌러서 바꾸기`" @click="cycle">
      <span aria-hidden="true">{{ theme === 'dark' ? '☾' : theme === 'light' ? '☀' : '◐' }}</span>
    </button>
    <button
      type="button"
      class="btn icon"
      :title="motion ? '장면 모션 켜짐' : '장면 모션 꺼짐'"
      :aria-pressed="!motion"
      aria-label="장면 모션 줄이기"
      @click="emit('update:motion', !motion)"
    >
      <span aria-hidden="true">{{ motion ? '≋' : '—' }}</span>
    </button>
  </div>
</template>

<style scoped>
.theme-controls { display: flex; gap: 6px; align-items: center; }
.icon { width: var(--tap); padding: 0; justify-content: center; font-size: 1.1rem; }
</style>
