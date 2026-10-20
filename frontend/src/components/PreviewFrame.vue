<script setup lang="ts">
import { computed } from 'vue'
import type { Preview } from '../api/types'

/**
 * 생성 앱 프리뷰. 부모 앱과 다른 hostname(별도 origin)일 때만 제한 iframe으로 연다.
 * allow-same-origin을 주지 않아 부모 쿠키·저장소·토큰에 접근할 수 없다. 같은 host의 다른 port는 신뢰하지 않는다.
 */
const props = defineProps<{
  preview: unknown
  /** 값이 있으면 기록으로만 표시하고 iframe을 만들지 않는다(재생·옛 후보·예시 등) */
  recordReason: string | null
}>()

const safe = computed<{ ok: true; preview: Preview } | { ok: false; reason: string }>(() => {
  const p = props.preview as Partial<Preview> | null
  if (!p || typeof p.url !== 'string' || typeof p.origin !== 'string' || typeof p.commit_sha !== 'string') {
    return { ok: false, reason: '프리뷰 주소가 제공되지 않았습니다. 현재 서버는 격리 프리뷰를 연결하지 않았습니다.' }
  }
  let url: URL
  let origin: URL
  try {
    url = new URL(p.url)
    origin = new URL(p.origin)
  } catch {
    return { ok: false, reason: '프리뷰 주소 형식이 올바르지 않습니다.' }
  }
  if (!['http:', 'https:'].includes(url.protocol) || url.origin !== origin.origin) {
    return { ok: false, reason: '프리뷰 주소가 선언된 origin과 다릅니다. 열지 않습니다.' }
  }
  if (url.hostname === window.location.hostname) {
    return { ok: false, reason: '프리뷰가 이 화면과 같은 hostname입니다. 쿠키 격리가 보장되지 않아 열지 않습니다.' }
  }
  return { ok: true, preview: p as Preview }
})
</script>

<template>
  <div class="preview">
    <div v-if="recordReason" class="info-box">
      <p><strong>기록된 프리뷰 — 지금 실행 중인 앱이 아닙니다.</strong> {{ recordReason }}</p>
      <dl v-if="typeof (preview as Preview | null)?.url === 'string'" class="kv small">
        <dt>기록 주소</dt><dd><code>{{ (preview as Preview).url }}</code></dd>
        <dt>커밋</dt><dd><code>{{ (preview as Preview).commit_sha }}</code></dd>
      </dl>
      <p v-else class="small muted">기록된 프리뷰 주소가 없습니다.</p>
    </div>
    <template v-else-if="safe.ok">
      <p class="small muted">격리 프리뷰 · {{ safe.preview.origin }} · 커밋 <code>{{ safe.preview.commit_sha.slice(0, 12) }}</code></p>
      <iframe
        :src="safe.preview.url"
        title="생성 앱 프리뷰"
        sandbox="allow-scripts allow-forms"
        referrerpolicy="no-referrer"
        loading="lazy"
      />
    </template>
    <p v-else class="info-box">{{ safe.reason }}</p>
  </div>
</template>

<style scoped>
.preview { display: grid; gap: 6px; }
iframe { width: 100%; height: min(60vh, 520px); border: 1px solid var(--line); border-radius: var(--radius); background: #fff; }
</style>
