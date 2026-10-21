<script setup lang="ts">
import { computed } from 'vue'
import type { PlanView } from '../api/types'
import { acCoverage, describeCheck } from '../model/planExtras'

/**
 * CR-C17 AC별 점검. AC마다 연결된 점검(선언형 명세)이나 사람 확인을 보이고, 둘 다 없는 AC는 눈에 띄게 표시한다.
 * 승인 차단은 서버 판정(implementation_allowed)을 따르며 이 구역은 표시만 한다.
 */
const props = defineProps<{ plan: PlanView }>()
const coverage = computed(() => acCoverage(props.plan))
</script>

<template>
  <section class="checks" aria-label="AC별 점검">
    <h3>AC별 점검</h3>
    <p v-if="coverage.kind === 'missing'" class="info-box small">미제공 · 미확인 — 서버가 이 기획의 점검 명세를 주지 않았습니다. AC가 검증된다고 보지 마세요.</p>
    <template v-else>
      <p v-if="coverage.uncoveredCount" class="error-box small" role="alert">
        점검도 사람 확인도 없는 AC가 {{ coverage.uncoveredCount }}개 AC 있습니다. 서버는 이런 기획의 구현 승인을 허용하지 않습니다.
      </p>
      <ul class="plain rows">
        <li v-for="r in coverage.rows" :key="r.ac.id" class="ac-row small" :class="{ uncovered: r.uncovered }">
          <strong>{{ r.ac.id }} · {{ r.ac.title }}</strong>
          <span v-for="c in r.checks" :key="c.id" class="check"><span class="chip">{{ describeCheck(c).kind }}</span> {{ describeCheck(c).text }}</span>
          <span v-if="r.manual" class="check"><span class="chip">사람 확인</span> {{ r.manual.reason }}</span>
          <span v-if="r.uncovered" class="gap">연결된 점검도 사람 확인도 없음</span>
        </li>
      </ul>
    </template>
  </section>
</template>

<style scoped>
.checks { display: grid; gap: 6px; }
.rows { display: grid; gap: 8px; }
.ac-row { display: grid; gap: 3px; padding: 8px 10px; border: 1px solid var(--line); border-radius: var(--radius); background: var(--surface); }
.ac-row.uncovered { border-color: var(--tone-danger); background: color-mix(in srgb, var(--tone-danger) 8%, var(--surface)); box-shadow: inset 3px 0 0 var(--tone-danger); }
.gap { color: var(--tone-danger); font-weight: 700; }
.check { word-break: break-word; }
</style>
