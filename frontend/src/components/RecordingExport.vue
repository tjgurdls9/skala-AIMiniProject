<script setup lang="ts">
import { ref } from 'vue'
import { ApiError, errorHint } from '../api/errors'
import type { RunSource } from '../api/source'
import { shortDigest } from '../model/labels'

/**
 * 공개 기록 내보내기(CODEX-RECORDING-001): 동결 snapshot·events·공개 artifact만 담긴 JSON 파일.
 * 키·작업 내부는 서버가 넣지 않고 비밀 형식이 검출되면 서버가 거절한다. 변경 요청·명세 등 사용자 입력은 들어갈 수 있다.
 * 합성 예시는 실제 기록이 아니므로 내보내지 않는다.
 */
const props = defineProps<{ source: RunSource; runId: string }>()

const busy = ref(false)
const error = ref<ApiError | null>(null)
const done = ref<string | null>(null)

async function exportRecording(): Promise<void> {
  if (busy.value) return
  busy.value = true
  error.value = null
  done.value = null
  try {
    const bundle = await props.source.getRecording()
    const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `recording-${props.runId.slice(0, 12)}.json`
    a.click()
    URL.revokeObjectURL(url)
    done.value = bundle.manifest_digest
  } catch (e) {
    error.value = e instanceof ApiError ? e : new ApiError(0, 'NETWORK', '기록을 내보내지 못했습니다.')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="panel export" aria-labelledby="export-title">
    <header><h2 id="export-title">기록 파일</h2></header>
    <p class="small muted">
      키·모델 없이 다른 환경에서 이 실행을 열어 볼 수 있는 공개 기록(JSON)입니다. 사용자 입력과 산출물이 들어 있을 수 있으니 공유 전에 내용을 확인하세요.
    </p>
    <button v-if="source.kind === 'live'" type="button" class="btn" :disabled="busy" @click="exportRecording">
      {{ busy ? '내보내는 중…' : '기록 내보내기' }}
    </button>
    <p v-else class="small muted">합성 예시는 실제 기록이 아니어서 내보내지 않습니다.</p>
    <p v-if="done" class="small" role="status">내보냄 · manifest <code>{{ shortDigest(done) }}</code></p>
    <div v-if="error" class="error-box small" role="alert">{{ error.message }} <p>{{ errorHint(error) }}</p></div>
  </section>
</template>

<style scoped>
.export { display: grid; gap: 8px; justify-items: start; }
</style>
