<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, useId, watch } from 'vue'

/** 네이티브 모달 dialog: 포커스 가두기·Esc 닫기는 브라우저가, 열기 전 포커스 복귀는 여기서 처리한다. */
const props = defineProps<{ open: boolean; title: string; subtitle?: string }>()
const emit = defineEmits<{ close: [] }>()

const el = ref<HTMLDialogElement | null>(null)
const titleId = useId()
let opener: HTMLElement | null = null

watch(
  () => props.open,
  async (open) => {
    await nextTick()
    const dialog = el.value
    if (!dialog) return
    if (open && !dialog.open) {
      opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
      dialog.showModal()
    } else if (!open && dialog.open) {
      dialog.close()
    }
  },
  { immediate: true },
)

/** 여는 버튼이 결정 뒤 사라졌으면 작업 공간 본문으로 포커스를 돌린다 */
function restoreFocus(): void {
  const target = opener?.isConnected ? opener : document.querySelector<HTMLElement>('#workspace-main, main, h1')
  target?.focus()
  opener = null
}

function onClose(): void {
  restoreFocus()
  if (props.open) emit('close')
}

onBeforeUnmount(() => {
  if (opener) restoreFocus()
})
</script>

<template>
  <dialog ref="el" class="sheet" :aria-labelledby="titleId" @close="onClose">
    <div class="sheet-head">
      <h2 :id="titleId">{{ title }}</h2>
      <p v-if="subtitle" class="small muted">{{ subtitle }}</p>
    </div>
    <div class="sheet-body"><slot /></div>
    <div class="sheet-foot"><slot name="foot" /></div>
  </dialog>
</template>
