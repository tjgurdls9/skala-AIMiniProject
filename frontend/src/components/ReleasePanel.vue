<script setup lang="ts">
import { computed } from 'vue'
import type { SourceKind } from '../api/source'
import { isReleaseView, OPERATION_ACTION, OPERATION_STATE, RELEASE_STATE, volumeText } from '../model/release'
import { formatTime, shortDigest } from '../model/labels'

/**
 * CR-C15 출시·복구 공개 근거(읽기 전용). 서버 원장의 기록만 보여 주며 실행·승인을 보내지 않는다.
 * 의도 기록(accepted)·확인된 결과·불명을 구분한다. 복구(rolled_back)는 첫 출시 공개 중단이며 이전 버전 복원이 아니다.
 */
const props = defineProps<{ view: unknown; error: string | null; kind: SourceKind }>()

const release = computed(() => (isReleaseView(props.view) ? props.view : null))
const invalid = computed(() => props.view !== null && props.view !== undefined && !release.value)
const state = computed(() => (release.value ? RELEASE_STATE[release.value.state] : null))
const time = (iso: string | null) => (iso ? formatTime(iso) : '기록 없음')
</script>

<template>
  <section class="panel release" aria-label="출시·복구">
    <header>
      <h2>출시·복구</h2>
      <span class="chip">실제 출시 실행 비활성 · 읽기 전용</span>
      <span v-if="kind === 'example'" class="chip">합성 예시</span>
    </header>
    <div v-if="error" class="error-box small" role="alert">출시 정보를 읽지 못했습니다. {{ error }}</div>
    <p v-else-if="invalid" class="error-box small" role="alert">출시 정보 형식이 계약과 맞지 않아 표시하지 않습니다.</p>
    <p v-else-if="!release" class="small muted">출시 정보 읽는 중…</p>
    <template v-else>
      <p>
        <strong :class="['tone', `tone-${state!.tone}`]">{{ state!.text }}</strong>
        <span class="small"> — {{ release.reason }}</span>
      </p>
      <p v-if="state!.note" class="small muted">{{ state!.note }}</p>

      <dl v-if="release.target || release.details" class="kv small">
        <template v-if="release.target">
        <dt>커밋</dt><dd><code>{{ release.target.commit_sha }}</code></dd>
        <dt>이미지 digest</dt><dd><code>{{ shortDigest(release.target.image_digest) }}</code></dd>
        <dt>명세</dt><dd><code>{{ release.target.spec_version_id }}</code></dd>
        <dt>환경 설정 해시</dt><dd><code>{{ shortDigest(release.target.environment_config_digest) }}</code></dd>
        <dt>복구 계획 해시</dt><dd><code>{{ shortDigest(release.target.rollback_manifest_digest) }}</code></dd>
        <dt>두 보고서</dt><dd><code v-for="id in release.target.review_report_ids" :key="id" class="id">{{ id }}</code></dd>
        </template>
        <template v-if="release.details">
        <dt>저장소</dt><dd><code>{{ release.details.repository.url }}</code> · branch <code>{{ release.details.repository.branch }}</code></dd>
        <dt>push 효과</dt>
        <dd>
          <strong v-if="release.details.repository.auto_deploy" class="tone tone-warn">push하면 자동 배포가 일어납니다</strong>
          <span v-else>push 시 자동 배포 없음</span>
        </dd>
        <dt>환경</dt><dd>{{ release.details.environment.label }} · 노출 범위 {{ release.details.environment.exposure }}</dd>
        <dt>이미지</dt><dd><code>{{ release.details.image_reference }}</code></dd>
        <dt>무료 정책</dt><dd>{{ release.details.free_policy }}</dd>
        <dt>복구 계획</dt><dd>첫 출시 공개 중단 · 데이터 볼륨 보존 · 스키마 이전 없음 (이전 버전 복원 아님)</dd>
        </template>
      </dl>

      <h3 class="small">작업 원장</h3>
      <p v-if="!release.operations.length" class="small muted">기록된 출시 작업이 없습니다.</p>
      <ul v-else class="plain ops">
        <li v-for="op in release.operations" :key="op.operation_id" class="op small">
          <span><strong>{{ OPERATION_ACTION[op.action] }}</strong> · <span :class="['tone', `tone-${OPERATION_STATE[op.state].tone}`]">{{ OPERATION_STATE[op.state].text }}</span> <span class="muted">({{ OPERATION_STATE[op.state].group }})</span></span>
          <span class="muted">의도 기록 {{ time(op.accepted_at) }} · 실제 조회 {{ time(op.observed_at) }}</span>
          <span>{{ op.reason }}</span>
          <span v-if="op.action === 'rollback' || op.volume_preserved !== null" class="muted">{{ volumeText(op.volume_preserved) }}</span>
          <code class="muted">{{ shortDigest(op.operation_id) }}</code>
        </li>
      </ul>
    </template>
  </section>
</template>

<style scoped>
.release header { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; }
.release h3 { margin: 10px 0 4px; color: var(--ink-3); }
.id + .id { margin-left: 6px; }
.ops { display: grid; gap: 8px; }
.op { display: grid; gap: 2px; }
</style>
