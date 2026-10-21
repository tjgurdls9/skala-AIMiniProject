<script setup lang="ts">
import { computed, ref } from 'vue'
import type { PlanView } from '../api/types'

/**
 * CR-C17 아이디어 대안 비교. 서버 값(요약·차이·위험)을 그대로 보이고 선택된 대안을 표시한다.
 * interactive면 다른 대안에 "이 대안으로 다시 기획"을 둔다. 승인과 다른 결정이라 확인 단계를 거쳐 request_changes로 보낸다.
 */
const props = defineProps<{ plan: PlanView; interactive?: boolean; busy?: boolean }>()
const emit = defineEmits<{ choose: [alternativeId: string] }>()

const alternatives = computed(() => (props.plan.alternatives ?? []) as Array<{ id: string; summary: string; differences: string; risks: string }>)
const selectedId = computed(() => props.plan.selected_alternative_id ?? null)
const pending = ref<string | null>(null)

function confirm(): void {
  if (!pending.value) return
  emit('choose', pending.value)
  pending.value = null
}
</script>

<template>
  <section class="alternatives" aria-label="아이디어 대안">
    <h3>아이디어 대안</h3>
    <p v-if="!alternatives.length" class="info-box small">미제공 · 미확인 — 서버가 이 기획의 대안을 주지 않았습니다. 다른 방법을 비교했다고 보지 마세요.</p>
    <template v-else>
      <ul class="plain alts">
        <li v-for="a in alternatives" :key="a.id" class="alt" :aria-current="a.id === selectedId">
          <header>
            <strong>{{ a.summary }}</strong>
            <span v-if="a.id === selectedId" class="chip selected">선택됨 · 이 기획이 구현하는 대안</span>
          </header>
          <dl class="kv small">
            <dt>차이</dt><dd>{{ a.differences }}</dd>
            <dt>위험</dt><dd>{{ a.risks }}</dd>
          </dl>
          <button v-if="interactive && a.id !== selectedId" type="button" class="btn small choose-alt" :disabled="busy" @click="pending = a.id">이 대안으로 다시 기획</button>
          <div v-if="pending === a.id" class="confirm" role="group" aria-label="대안 변경 확인">
            <p class="small">현재 기획은 취소되고 이 대안으로 다시 기획합니다. 새 승인이 필요합니다. (승인이 아니라 수정 요청입니다)</p>
            <button type="button" class="btn small primary" :disabled="busy" @click="confirm">이 대안으로 보내기</button>
            <button type="button" class="btn small" @click="pending = null">취소</button>
          </div>
        </li>
      </ul>
      <p v-if="plan.single_alternative_reason" class="small">
        <strong>대안이 하나뿐인 이유</strong> — {{ plan.single_alternative_reason }}
      </p>
      <p v-else-if="alternatives.length === 1" class="info-box small">대안이 하나뿐인 이유가 없습니다(미제공).</p>
    </template>
  </section>
</template>

<style scoped>
.alternatives { display: grid; gap: 8px; }
.alts { display: grid; gap: 10px; }
.alt { display: grid; gap: 6px; padding: 10px 12px; border: 1px solid var(--line); border-radius: var(--radius); background: var(--surface); }
.alt[aria-current="true"] { border-color: var(--tone-ok); box-shadow: inset 3px 0 0 var(--tone-ok); }
.alt header { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 10px; }
.selected { color: var(--tone-ok); }
.choose-alt { justify-self: start; }
.confirm { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 8px 10px; border-radius: var(--radius); background: var(--surface-2); }
.confirm p { margin: 0; flex: 1 1 260px; }
</style>
