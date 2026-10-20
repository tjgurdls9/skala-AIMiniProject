<script setup lang="ts">
import { computed } from 'vue'
import type { Snapshot } from '../api/types'
import { shortDigest, VERDICT } from '../model/labels'
import { reviewRounds, roundOutcome } from '../model/reviews'

/** 후보별 검토 회차. 현재 회차와 과거 회차를 구분하고, 과거 원본 보고서도 열 수 있게 둔다. */
const props = defineProps<{ snapshot: Snapshot }>()
const emit = defineEmits<{ artifact: [id: string] }>()

const OUTCOME = {
  both_pass: { text: '두 검토 통과', tone: 'ok' },
  blocked: { text: '출시 차단 (한쪽 이상 통과 아님)', tone: 'danger' },
  waiting: { text: '다른 검토 제출 대기', tone: 'warn' },
} as const

const rounds = computed(() => [...reviewRounds(props.snapshot)].reverse())
</script>

<template>
  <div class="rounds">
    <p v-if="!rounds.length" class="small muted">아직 제출된 검토 보고서가 없습니다.</p>
    <ol class="plain">
      <li v-for="(round, i) in rounds" :key="`${round.key}-${i}`" :class="['round', { past: !round.isCurrent }]">
        <p class="head small">
          <strong>{{ round.isCurrent ? '현재 회차' : '과거 회차' }}</strong>
          · 커밋 <code>{{ shortDigest(round.commit) }}</code> · 이미지 <code>{{ shortDigest(round.image) }}</code>
          · 명세 <code>{{ round.spec }}</code>
          <span v-if="!round.specMatches" class="tone tone-warn">(현재 명세와 다름)</span>
        </p>
        <p :class="['tone', `tone-${OUTCOME[roundOutcome(round)].tone}`, 'small']">{{ OUTCOME[roundOutcome(round)].text }}</p>
        <ul class="plain verdicts small">
          <li v-for="[role, label] in ([['validator', '검증'], ['security', '보안']] as const)" :key="role">
            {{ label }}:
            <template v-if="round[role]">
              <span :class="['tone', `tone-${VERDICT[round[role]!.verdict].tone}`]">{{ VERDICT[round[role]!.verdict].glyph }} {{ VERDICT[round[role]!.verdict].text }}</span>
              <button type="button" class="link" @click="emit('artifact', round[role]!.artifact_id)">원본</button>
            </template>
            <span v-else class="muted">제출 전 또는 비공개</span>
          </li>
        </ul>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.round { padding: 8px 0; border-bottom: 1px solid var(--line); display: grid; gap: 2px; }
.round.past { opacity: 0.8; }
.verdicts { display: flex; flex-wrap: wrap; gap: 4px 16px; }
.link { border: 0; background: none; color: var(--focus); text-decoration: underline; cursor: pointer; min-height: 32px; padding: 0 4px; }
</style>
