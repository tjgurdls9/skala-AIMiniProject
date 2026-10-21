<script setup lang="ts">
import type { PlanView } from '../api/types'
import { shortDigest } from '../model/labels'
import { supportVerdict } from '../model/planSupport'
import PlanSupportBody from './PlanSupportBody.vue'

/**
 * 기획 패키지(http.PlanView) 읽기 전용 표시. 저장소·배포 대상 null은 미설정이며 외부 부작용을 허용하지 않는다.
 * CR-C14 지원 공백도 함께 읽기 전용으로 보여 준다. 승인 화면은 결정용 지원 구역을 따로 그리므로 showSupport=false로 끈다.
 */
withDefaults(defineProps<{ plan: PlanView; showSupport?: boolean }>(), { showSupport: true })
</script>

<template>
  <div class="plan">
    <PlanSupportBody v-if="showSupport" :verdict="supportVerdict(plan)" read-only />
    <section>
      <h3>목표</h3>
      <p>{{ plan.goal }}</p>
    </section>
    <div class="cols">
      <section>
        <h3>기능</h3>
        <ul><li v-for="f in plan.features" :key="f">{{ f }}</li></ul>
      </section>
      <section>
        <h3>비범위</h3>
        <ul><li v-for="f in plan.non_goals" :key="f">{{ f }}</li></ul>
        <p v-if="!plan.non_goals.length" class="muted">없음</p>
      </section>
    </div>
    <section>
      <h3>인수 기준</h3>
      <ol class="plain ac">
        <li v-for="ac in plan.acceptance" :key="ac.id"><strong>{{ ac.id }} · {{ ac.title }}</strong><br />{{ ac.description }}</li>
      </ol>
    </section>
    <section v-if="plan.changes.length" class="changes">
      <h3>원문 대비 변경 설명</h3>
      <ul><li v-for="c in plan.changes" :key="c">{{ c }}</li></ul>
      <p class="small muted">모델이 작성한 설명입니다. 원문 대조 검증 결과가 아닙니다. 최초 요청 원문은 서버 원장에 보존됩니다.</p>
    </section>
    <div class="cols">
      <section>
        <h3>제약</h3>
        <ul><li v-for="c in plan.constraints" :key="c">{{ c }}</li></ul>
      </section>
      <section>
        <h3>가정</h3>
        <ul><li v-for="a in plan.assumptions" :key="a">{{ a }}</li></ul>
      </section>
    </div>
    <dl class="kv">
      <dt>스택</dt><dd>{{ plan.stack.join(', ') || '—' }}</dd>
      <dt>저장소</dt>
      <dd>
        <template v-if="plan.repository"><code>{{ plan.repository.url }}</code> · 브랜치 <code>{{ plan.repository.branch }}</code></template>
        <span v-else class="tone tone-warn">미설정 — 저장소 쓰기·푸시를 허용하지 않음</span>
      </dd>
      <dt>배포 대상</dt>
      <dd>
        <template v-if="plan.deployment">{{ plan.deployment.label }} (<code>{{ plan.deployment.id }}</code>, 노출 {{ plan.deployment.exposure }})</template>
        <span v-else class="tone tone-warn">미설정 — 배포를 허용하지 않음</span>
      </dd>
      <dt>무료 정책</dt><dd>{{ plan.free_policy }}</dd>
      <dt>허용 도구</dt><dd>{{ plan.allowed_tools.join(', ') || '—' }}</dd>
      <dt>명세 버전</dt><dd><code>{{ plan.spec_version_id }}</code></dd>
      <dt>계약 해시</dt>
      <dd><span v-for="(d, name) in plan.contract_digests" :key="name" class="digest"><code>{{ name }} {{ shortDigest(d) }}</code></span></dd>
    </dl>
  </div>
</template>

<style scoped>
.plan { display: grid; gap: 14px; }
h3 { font-size: 0.85rem; color: var(--ink-3); margin-bottom: 4px; }
ul { margin: 0; padding-left: 1.2em; }
.cols { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; }
.ac li { padding: 6px 0; border-bottom: 1px solid var(--line); }
.changes { border-left: 3px solid var(--tone-warn); padding-left: 10px; }
.digest { display: block; }
</style>
