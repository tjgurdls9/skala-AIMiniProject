<script setup lang="ts">
import type { ContextEvidence, RetrievalEvidence } from '../api/types'
import { RETRIEVAL_ERROR, RETRIEVAL_STATUS, safeHttpUrl } from '../model/evidence'
import { formatTime, ROLE, shortDigest } from '../model/labels'

/**
 * CR-C12 공개 근거 본문. 검색 근거는 실제 방법(키워드/의미)·상태·출처를, 문맥 근거는 원문 조각의 위치·해시를 보여 준다.
 * 관련도 점수는 충족·검사 판정이 아니다. 오류를 빈 결과로 바꾸지 않는다.
 */
defineProps<{ retrieval?: RetrievalEvidence; context?: ContextEvidence }>()

function roleNames(roles: RetrievalEvidence['sources'][number]['roles']): string {
  return roles.map((r) => ROLE[r].text).join(', ')
}
</script>

<template>
  <div v-if="retrieval" class="evidence-body">
    <p :class="['tone', `tone-${RETRIEVAL_STATUS[retrieval.status].tone}`]">
      {{ RETRIEVAL_STATUS[retrieval.status].glyph }} {{ RETRIEVAL_STATUS[retrieval.status].text }}
      <span v-if="retrieval.status === 'search_error' && retrieval.error_code" class="small">· {{ RETRIEVAL_ERROR[retrieval.error_code] }}</span>
    </p>
    <dl class="kv small">
      <dt>검색한 역할</dt><dd>{{ ROLE[retrieval.role].text }}</dd>
      <dt>방법</dt><dd>{{ retrieval.method === 'semantic' ? `의미 검색 · ${retrieval.model ?? '모델 미표기'}` : '키워드 검색' }}</dd>
    </dl>
    <ol v-if="retrieval.sources.length" class="plain sources">
      <li v-for="s in retrieval.sources" :key="s.chunk_id" class="source">
        <a v-if="safeHttpUrl(s.url)" :href="safeHttpUrl(s.url)!" target="_blank" rel="noopener noreferrer">{{ s.url }}</a>
        <code v-else>{{ s.url }}</code>
        <p class="small muted">
          버전 {{ s.version }} · {{ s.license }} · 수집 {{ formatTime(s.collected_at) }} · 본문 <code>{{ shortDigest(s.content_digest) }}</code>
        </p>
        <p class="small muted">
          허용 역할 {{ roleNames(s.roles) }} · 관련도 {{ s.score.toFixed(2) }} <span>(판정 아님)</span>
        </p>
      </li>
    </ol>
    <p v-else class="small muted">{{ retrieval.status === 'search_error' ? '검색이 실패해 근거가 없습니다.' : '조건에 맞는 근거가 없습니다.' }}</p>
  </div>

  <div v-else-if="context" class="evidence-body">
    <p :class="['tone', context.status === 'ready' ? 'tone-ok' : 'tone-warn']">
      {{ context.status === 'ready' ? '✓ 문맥 준비됨' : '? 입력 필요' }}
      <span class="small">· 조각 {{ context.completed_fragments }} / {{ context.total_fragments }}</span>
    </p>
    <dl class="kv small">
      <dt>명세</dt><dd><code>{{ context.spec_version_id ?? '미확정' }}</code></dd>
      <dt>원문 해시</dt><dd><code>{{ shortDigest(context.source_digest) }}</code></dd>
    </dl>
    <ol v-if="context.sources.length" class="plain sources">
      <li v-for="(s, i) in context.sources" :key="`${s.request_id}-${s.offset}-${i}`" class="source small">
        요청 <code>{{ s.request_id.slice(0, 8) }}</code> · 위치 {{ s.offset }}–{{ s.offset + s.length }}(문자) · <code>{{ shortDigest(s.content_digest) }}</code>
      </li>
    </ol>
    <p class="small muted">원문과 정정은 원장에 그대로 남습니다. 이 근거는 위치와 해시만 보여 주며 승인 증거가 아닙니다.</p>
  </div>
</template>

<style scoped>
.evidence-body { display: grid; gap: 6px; }
.sources { display: grid; gap: 8px; }
.source { padding: 8px 10px; border: 1px solid var(--line); border-radius: 8px; overflow-wrap: anywhere; }
.source a { color: var(--focus); font-weight: 600; }
</style>
