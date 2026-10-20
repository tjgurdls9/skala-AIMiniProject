<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ApiError, errorHint } from '../api/errors'
import type { LiveApi } from '../api/live'
import type { ReplayRecording, Runtime } from '../api/types'
import { SCENARIOS } from '../examples/scenarios'
import { formatTime, shortDigest } from '../model/labels'
import ThemeControls from './ThemeControls.vue'

/** 빈 사무실: 최초 요청 → 새 LIVE, 실제 기록 REPLAY, 합성 예시를 명시적으로 고른다. LIVE 오류 시 예시로 자동 전환하지 않는다. */
const props = defineProps<{ api: LiveApi }>()
const emit = defineEmits<{ openRun: [runId: string]; openExample: [id: string] }>()

const runtime = ref<Runtime | null>(null)
const replays = ref<ReplayRecording[] | null>(null)
const serverError = ref<ApiError | null>(null)
const title = ref('')
const request = ref('')
const submitting = ref(false)
const submitError = ref<ApiError | null>(null)
const motion = ref(true)

const MODEL_STATUS: Record<Runtime['model_status'], string> = { not_configured: '미설정', unavailable: '연결 안 됨', ready: '준비됨' }
const RUNNER_STATUS: Record<Runtime['runner_status'], string> = { unavailable: '연결 안 됨', ready: '준비됨' }

async function load(): Promise<void> {
  serverError.value = null
  try {
    await props.api.connect()
    const [rt, rp] = await Promise.all([props.api.getRuntime(), props.api.listReplays()])
    runtime.value = rt
    replays.value = rp
  } catch (error) {
    serverError.value = error instanceof ApiError ? error : new ApiError(0, 'NETWORK', '서버에 연결하지 못했습니다.')
  }
}

async function startLive(): Promise<void> {
  if (submitting.value) return
  submitting.value = true
  submitError.value = null
  try {
    const project = await props.api.createProject({ title: title.value.trim(), request: request.value.trim() })
    const snapshot = await props.api.createRun(project.project_id, { mode: 'live' })
    emit('openRun', snapshot.run_id)
  } catch (error) {
    submitError.value = error instanceof ApiError ? error : new ApiError(0, 'NETWORK', '실행을 만들지 못했습니다.')
  } finally {
    submitting.value = false
  }
}

async function startReplay(rec: ReplayRecording): Promise<void> {
  submitError.value = null
  try {
    const snapshot = await props.api.createRun(rec.project_id, { mode: 'replay', source_run_id: rec.source_run_id })
    emit('openRun', snapshot.run_id)
  } catch (error) {
    submitError.value = error instanceof ApiError ? error : new ApiError(0, 'NETWORK', '재생을 만들지 못했습니다.')
  }
}

onMounted(load)
</script>

<template>
  <div class="start">
    <header class="top">
      <div>
        <h1>개발 사무실</h1>
        <p class="muted">요청 → 기획 승인 → 구현 → 독립 검증·보안 → 프리뷰 → 배포 승인을 한 화면에서 따라갑니다.</p>
      </div>
      <ThemeControls v-model:motion="motion" />
    </header>

    <main class="grid">
      <section class="panel request" aria-labelledby="req-title">
        <header><h2 id="req-title">새 요청 · LIVE 실행</h2></header>
        <form class="form" @submit.prevent="startLive">
          <label class="field">
            제목
            <input v-model="title" type="text" maxlength="200" required />
          </label>
          <label class="field">
            무엇을 만들까요?
            <span class="hint small muted">원문은 그대로 보존되고, 기획 단계에서 목표·범위·인수 기준으로 정리됩니다.</span>
            <textarea v-model="request" maxlength="32000" rows="6" required />
          </label>
          <p v-if="runtime && !runtime.live_available" class="info-box small">
            지금은 LIVE 실행을 시작할 수 없습니다. {{ runtime.reasons.join(' · ') || '실행 환경이 준비되지 않았습니다.' }}
            실제 기록 재생이나 합성 예시는 볼 수 있습니다.
          </p>
          <div v-if="submitError" class="error-box" role="alert">{{ submitError.message }} <p class="small">{{ errorHint(submitError) }}</p></div>
          <button
            type="submit"
            class="btn primary"
            :disabled="submitting || !runtime?.live_available || !title.trim() || !request.trim()"
          >
            {{ submitting ? '만드는 중…' : '새 LIVE 실행 시작' }}
          </button>
        </form>
      </section>

      <section class="panel" aria-labelledby="rt-title">
        <header><h2 id="rt-title">실행 가능성</h2><button type="button" class="btn small" @click="load">다시 확인</button></header>
        <div v-if="serverError" class="error-box" role="alert">
          서버에 연결하지 못했습니다: {{ serverError.message }}
          <p class="small">{{ errorHint(serverError) }} 합성 예시는 서버 없이 볼 수 있습니다(자동 전환하지 않음).</p>
        </div>
        <dl v-else-if="runtime" class="kv">
          <dt>모델 공급자</dt><dd>로컬 Ollama · 무료 전용 (외부 API {{ runtime.external_api_enabled ? '사용' : '사용 안 함' }})</dd>
          <dt>모델</dt><dd>{{ runtime.model ?? '미지정' }} · <strong>{{ MODEL_STATUS[runtime.model_status] }}</strong></dd>
          <dt>작업 실행기</dt><dd><strong>{{ RUNNER_STATUS[runtime.runner_status] }}</strong></dd>
          <dt>추론 슬롯</dt><dd>{{ runtime.inference_slots }}</dd>
          <dt>배포</dt><dd>{{ runtime.deployment_enabled ? '사용 가능' : '비활성 (배포 대상 미연결)' }}</dd>
          <dt>LIVE</dt><dd :class="runtime.live_available ? 'tone-ok' : 'tone-warn'">{{ runtime.live_available ? '시작 가능' : '불가' }}</dd>
        </dl>
        <p v-else class="muted">확인 중…</p>
        <ul v-if="runtime?.reasons.length" class="small reasons">
          <li v-for="r in runtime.reasons" :key="r">{{ r }}</li>
        </ul>
      </section>

      <section class="panel" aria-labelledby="replay-title">
        <header><h2 id="replay-title">실제 기록 재생</h2><span class="chip">읽기 전용</span></header>
        <p class="small muted">이전 LIVE 실행의 실제 원장을 새 명령 없이 다시 봅니다.</p>
        <ul v-if="replays?.length" class="plain list">
          <li v-for="r in replays" :key="r.source_run_id">
            <button type="button" class="btn item" @click="startReplay(r)">
              <span><strong>{{ r.title }}</strong><br /><span class="small muted">{{ formatTime(r.recorded_at) }} · manifest <code>{{ shortDigest(r.manifest_digest) }}</code></span></span>
            </button>
          </li>
        </ul>
        <p v-else-if="replays" class="muted">아직 실제 기록이 없습니다.</p>
        <p v-else class="muted">서버 연결 후 표시됩니다.</p>
      </section>

      <section class="panel examples" aria-labelledby="ex-title">
        <header><h2 id="ex-title">합성 예시</h2><span class="chip example">실제 실행 아님</span></header>
        <p class="small muted">화면 상태를 확인하기 위한 합성 데이터입니다. 서버를 쓰지 않으며 명령·승인·배포를 보내지 않습니다.</p>
        <ul class="plain list">
          <li v-for="s in SCENARIOS" :key="s.id">
            <button type="button" class="btn item" @click="emit('openExample', s.id)">
              <span><strong>[예시] {{ s.label }}</strong><br /><span class="small muted">{{ s.description }}</span></span>
            </button>
          </li>
        </ul>
      </section>
    </main>
  </div>
</template>

<style scoped>
.start { max-width: 1280px; margin: 0 auto; padding: 24px 16px 40px; display: grid; gap: 20px; }
.top { display: flex; flex-wrap: wrap; gap: 12px; justify-content: space-between; align-items: flex-end; }
h1 { font-size: 1.6rem; }
.grid { display: grid; gap: var(--gap); grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr); }
.request { grid-row: span 2; }
.form { display: grid; gap: 14px; }
.form .btn.primary { justify-self: start; }
.list { display: grid; gap: 6px; }
.item { width: 100%; height: auto; padding: 10px 12px; text-align: left; white-space: normal; justify-content: flex-start; }
.reasons { margin: 8px 0 0; padding-left: 1.2em; color: var(--ink-2); }
.examples { grid-column: 1 / -1; }
.examples .list { grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); }
.chip.example { color: var(--example); background: var(--example-bg); border-color: currentColor; }
@media (max-width: 860px) { .grid { grid-template-columns: minmax(0, 1fr); } .request { grid-row: auto; } }
</style>
