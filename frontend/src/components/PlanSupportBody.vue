<script setup lang="ts">
import { EXTERNAL_STATUS, NEED_NAME, type PlanSupport, type SupportVerdict } from '../model/planSupport'
import { shortDigest } from '../model/labels'

/**
 * CR-C14 기획별 지원 공백. 비범위(non_goals)와 섞지 않고 별도 구역에 서버 값을 그대로 보여 준다.
 * readOnly: 기획 아티팩트·재생에서 읽기만 할 때. 결정 안내와 다시 읽기 버튼을 빼고 서버 판정임을 밝힌다.
 */
defineProps<{ verdict: SupportVerdict; readOnly?: boolean }>()
const emit = defineEmits<{ reload: [] }>()

const needNames = (needs: PlanSupport['external'][number]['needs']) => needs.map((n) => NEED_NAME[n]).join(', ')
</script>

<template>
  <section class="support" aria-label="지원 범위와 공백">
    <h3>지원 범위와 공백</h3>
    <p v-if="verdict.kind === 'missing'" class="info-box small">
      지원 정보 미제공 · 미확인 — 서버가 이 기획의 지원 범위를 주지 않았습니다. 지원되는 요청으로 보지 마세요.
    </p>
    <div v-else-if="verdict.kind === 'mismatch'" class="error-box small" role="alert">
      지원 정보의 명세 버전({{ verdict.specVersionId }})이 기획과 달라 표시하지 않습니다.
      <button v-if="!readOnly" type="button" class="btn small" @click="emit('reload')">다시 읽기</button>
    </div>
    <template v-else>
      <p class="small">
        템플릿 <code>{{ verdict.support.template_id }}</code>
        · 요청 묶음 <code>{{ shortDigest(verdict.support.request_digest) }}</code>
      </p>
      <p v-if="verdict.kind === 'blocked' && readOnly" class="info-box small">
        이 기획은 지원 공백 때문에 구현 승인 불가로 판정돼 있습니다(서버 판정 · 읽기 전용).
      </p>
      <p v-else-if="verdict.kind === 'blocked'" class="error-box small" role="alert">
        현재 공백 때문에 구현 승인을 보낼 수 없습니다. 수정 요청(거절)으로 다시 기획할 수 있습니다.
      </p>
      <p v-else-if="!verdict.support.unsupported.length && !verdict.support.external.length" class="small">
        <strong class="tone tone-ok">알려진 지원 공백 없음</strong>
        <span class="muted"> — AC 충족이나 검토·출시 수용을 뜻하지 않습니다.<template v-if="!readOnly"> 승인은 직접 판단하세요.</template></span>
      </p>

      <template v-if="verdict.support.unsupported.length">
        <h4 class="small">요청했지만 지원하지 않는 것</h4>
        <ul class="plain gaps">
          <li v-for="(u, i) in verdict.support.unsupported" :key="i" class="small">
            <span class="quote">“{{ u.request_quote }}”</span>
            <span>{{ u.reason }}</span>
            <span v-if="u.requires.length" class="muted">필요: {{ u.requires.join(', ') }}</span>
          </li>
        </ul>
      </template>
      <template v-if="verdict.support.external.length">
        <h4 class="small">외부 의존</h4>
        <ul class="plain gaps">
          <li v-for="(e, i) in verdict.support.external" :key="i" class="small">
            <span><strong>{{ e.purpose }}</strong> · {{ e.provider ?? '공급자 미정' }} · <span :class="['tone', `tone-${EXTERNAL_STATUS[e.status].tone}`]">{{ EXTERNAL_STATUS[e.status].text }}</span></span>
            <span v-if="e.needs.length" class="muted">필요: {{ needNames(e.needs) }}</span>
            <span>{{ e.reason }}</span>
          </li>
        </ul>
      </template>
    </template>
  </section>
</template>

<style scoped>
.support { display: grid; gap: 6px; margin: 12px 0; }
.support h3 { font-size: 0.9rem; color: var(--ink-3); }
.support h4 { margin: 6px 0 2px; color: var(--ink-3); }
.gaps { display: grid; gap: 8px; }
.gaps li { display: grid; gap: 2px; }
.quote { font-weight: 600; }
</style>
