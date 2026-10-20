<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { ApiError, errorHint } from '../api/errors'
import type { LiveApi } from '../api/live'
import type { ReplayRecording, Runtime } from '../api/types'
import { SCENARIOS } from '../examples/scenarios'
import { formatTime, shortDigest } from '../model/labels'
import BaseDialog from './BaseDialog.vue'
import ThemeControls from './ThemeControls.vue'
import { titleFrom, type Origin } from '../model/prompt'

/**
 * 빈 화면 + 굵은 문구 하나 + 입력창 하나(사용자 디자인 지시).
 * 실행 가능성·실제 기록 재생·합성 예시는 입력 아래의 조용한 링크로 연다. LIVE 오류 시 예시로 자동 전환하지 않는다.
 */
const props = defineProps<{ api: LiveApi }>()
const emit = defineEmits<{ openRun: [runId: string, origin: Origin]; openExample: [id: string, origin: Origin] }>()

const runtime = ref<Runtime | null>(null)
const replays = ref<ReplayRecording[] | null>(null)
const serverError = ref<ApiError | null>(null)
const request = ref('')
const submitting = ref(false)
const submitError = ref<ApiError | null>(null)
const motion = ref(true)
const moreOpen = ref(false)
const field = ref<HTMLTextAreaElement | null>(null)
/** 프로젝트는 만들었는데 실행 생성이 실패한 경우, 재시도에서 같은 프로젝트를 다시 쓴다(중복 생성 방지) */
const createdProject = ref<{ key: string; id: string } | null>(null)

const MODEL_STATUS: Record<Runtime['model_status'], string> = { not_configured: '미설정', unavailable: '연결 안 됨', ready: '준비됨' }
const RUNNER_STATUS: Record<Runtime['runner_status'], string> = { unavailable: '연결 안 됨', ready: '준비됨' }

/** 입력이 왜 지금 실행될 수 없는지(없으면 null). 버튼만 막고 이유를 입력 아래에 그대로 보여 준다 */
const blocked = computed<string | null>(() => {
  if (serverError.value) return `서버에 연결하지 못했습니다 — ${serverError.value.message}`
  if (!runtime.value) return '실행 가능성을 확인하는 중입니다.'
  if (!runtime.value.live_available) return `지금은 LIVE 실행을 시작할 수 없습니다 — ${runtime.value.reasons[0] ?? '실행 환경이 준비되지 않았습니다.'}`
  return null
})

function originOf(el: Element | null): Origin {
  const r = el?.getBoundingClientRect()
  return r ? { x: r.left + r.width / 2, y: r.top + r.height / 2 } : { x: window.innerWidth / 2, y: window.innerHeight / 2 }
}

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
  const text = request.value.trim()
  if (submitting.value || !text || blocked.value) return
  submitting.value = true
  submitError.value = null
  try {
    const key = text
    if (createdProject.value?.key !== key) {
      const project = await props.api.createProject({ title: titleFrom(text), request: text })
      createdProject.value = { key, id: project.project_id }
    }
    const snapshot = await props.api.createRun(createdProject.value.id, { mode: 'live' })
    emit('openRun', snapshot.run_id, originOf(field.value))
  } catch (error) {
    submitError.value = error instanceof ApiError ? error : new ApiError(0, 'NETWORK', '실행을 만들지 못했습니다.')
  } finally {
    submitting.value = false
  }
}

async function startReplay(rec: ReplayRecording, e: MouseEvent): Promise<void> {
  if (submitting.value) return
  submitting.value = true
  submitError.value = null
  try {
    const snapshot = await props.api.createRun(rec.project_id, { mode: 'replay', source_run_id: rec.source_run_id })
    emit('openRun', snapshot.run_id, { x: e.clientX, y: e.clientY })
  } catch (error) {
    submitError.value = error instanceof ApiError ? error : new ApiError(0, 'NETWORK', '재생을 만들지 못했습니다.')
  } finally {
    submitting.value = false
  }
}

/** Enter로 보내고 Shift+Enter는 줄바꿈. 한글 조합 중 Enter는 무시한다 */
function onKeydown(e: KeyboardEvent): void {
  if (e.key !== 'Enter' || e.shiftKey || e.isComposing) return
  e.preventDefault()
  void startLive()
}

function autoGrow(): void {
  const el = field.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 220)}px`
}

onMounted(async () => {
  void load()
  await nextTick()
  field.value?.focus()
})
</script>

<template>
  <div class="start">
    <div class="corner"><ThemeControls v-model:motion="motion" /></div>

    <main class="center">
      <h1 id="start-title" class="headline">무엇을 만들까요?</h1>
      <form class="prompt" aria-labelledby="start-title" @submit.prevent="startLive">
        <label for="prompt-input" class="sr-only">만들고 싶은 서비스 설명</label>
        <textarea
          id="prompt-input"
          ref="field"
          v-model="request"
          rows="1"
          maxlength="32000"
          placeholder="예: 고객 문의를 분류하고 처리 상태를 관리하는 작은 대시보드"
          aria-describedby="prompt-hint"
          @keydown="onKeydown"
          @input="autoGrow"
        />
        <button type="submit" class="send" :disabled="submitting || !request.trim() || !!blocked" :aria-label="submitting ? '사무실 여는 중' : '시작'">
          <span aria-hidden="true">{{ submitting ? '…' : '→' }}</span>
        </button>
      </form>
      <p id="prompt-hint" class="hint" :class="{ warn: blocked && runtime !== null || serverError }">
        <template v-if="blocked && (runtime || serverError)">{{ blocked }}</template>
        <template v-else>Enter로 시작 · Shift+Enter 줄바꿈 · 원문은 그대로 보존되고 기획 승인 전에는 구현이 시작되지 않습니다</template>
      </p>
      <div v-if="submitError" class="error-box" role="alert">{{ submitError.message }} <p class="small">{{ errorHint(submitError) }}</p></div>
      <button type="button" class="more" @click="moreOpen = true">실행 가능성 · 실제 기록 재생 · 합성 예시</button>
    </main>

    <BaseDialog :open="moreOpen" title="다른 방법으로 보기" subtitle="LIVE 조건 확인, 실제 기록 재생(읽기 전용), 합성 예시(실제 실행 아님)" @close="moreOpen = false">
      <section aria-labelledby="rt-title">
        <h3 id="rt-title">실행 가능성 <button type="button" class="btn small" @click="load">다시 확인</button></h3>
        <div v-if="serverError" class="error-box">{{ serverError.message }} <p class="small">{{ errorHint(serverError) }}</p></div>
        <dl v-else-if="runtime" class="kv">
          <dt>모델 공급자</dt><dd>로컬 Ollama · 무료 전용 (외부 API {{ runtime.external_api_enabled ? '사용' : '사용 안 함' }})</dd>
          <dt>모델</dt><dd>{{ runtime.model ?? '미지정' }} · <strong>{{ MODEL_STATUS[runtime.model_status] }}</strong></dd>
          <dt>작업 실행기</dt><dd><strong>{{ RUNNER_STATUS[runtime.runner_status] }}</strong></dd>
          <dt>배포</dt><dd>{{ runtime.deployment_enabled ? '사용 가능' : '비활성 (배포 대상 미연결)' }}</dd>
          <dt>LIVE</dt><dd :class="runtime.live_available ? 'tone-ok' : 'tone-warn'">{{ runtime.live_available ? '시작 가능' : '불가' }}</dd>
        </dl>
        <p v-else class="muted">확인 중…</p>
        <ul v-if="runtime?.reasons.length" class="small reasons">
          <li v-for="r in runtime.reasons" :key="r">{{ r }}</li>
        </ul>
      </section>
      <section aria-labelledby="replay-title">
        <h3 id="replay-title">실제 기록 재생 <span class="chip">읽기 전용</span></h3>
        <ul v-if="replays?.length" class="plain list">
          <li v-for="r in replays" :key="r.source_run_id">
            <button type="button" class="btn item" :disabled="submitting" @click="startReplay(r, $event)">
              <span><strong>{{ r.title }}</strong><br /><span class="small muted">{{ formatTime(r.recorded_at) }} · manifest <code>{{ shortDigest(r.manifest_digest) }}</code></span></span>
            </button>
          </li>
        </ul>
        <p v-else-if="replays" class="muted">아직 실제 기록이 없습니다.</p>
        <p v-else class="muted">서버 연결 후 표시됩니다.</p>
      </section>
      <section aria-labelledby="ex-title">
        <h3 id="ex-title">합성 예시 <span class="chip example">실제 실행 아님</span></h3>
        <ul class="plain list grid">
          <li v-for="s in SCENARIOS" :key="s.id">
            <button type="button" class="btn item" @click="emit('openExample', s.id, { x: $event.clientX, y: $event.clientY })">
              <span><strong>[예시] {{ s.label }}</strong><br /><span class="small muted">{{ s.description }}</span></span>
            </button>
          </li>
        </ul>
      </section>
      <template #foot>
        <button type="button" class="btn" @click="moreOpen = false">닫기</button>
      </template>
    </BaseDialog>
  </div>
</template>

<style scoped>
.start { min-height: 100dvh; display: grid; place-items: center; padding: 24px 16px; position: relative; }
.corner { position: absolute; top: 16px; right: 16px; }
.center { width: min(760px, 100%); display: grid; gap: 18px; justify-items: center; text-align: center; }
.headline {
  font-size: clamp(2.5rem, 1.2rem + 6vw, 5.5rem);
  font-weight: 900;
  letter-spacing: -0.04em;
  line-height: 1.02;
}
.prompt {
  width: 100%;
  display: flex; align-items: flex-end; gap: 8px;
  padding: 10px 10px 10px 20px;
  border: 2px solid var(--ink); border-radius: 22px;
  background: var(--surface);
  box-shadow: 0 10px 30px rgb(0 0 0 / 0.08);
}
.prompt:focus-within { box-shadow: 0 0 0 4px color-mix(in srgb, var(--focus) 35%, transparent), 0 10px 30px rgb(0 0 0 / 0.08); }
.prompt textarea {
  flex: 1; min-height: 44px; max-height: 220px; padding: 10px 0; border: 0; background: none; resize: none;
  font-size: 1.15rem; line-height: 1.5;
}
.prompt textarea:focus { outline: none; }
.send {
  width: 48px; height: 48px; flex: none; border-radius: 16px; border: 0;
  background: var(--ink); color: var(--bg); font-size: 1.4rem; font-weight: 800; cursor: pointer;
}
.send:disabled { opacity: 0.35; cursor: not-allowed; }
.hint { color: var(--ink-3); font-size: 0.9rem; max-width: 640px; }
.hint.warn { color: var(--tone-warn); font-weight: 600; }
.more {
  min-height: var(--tap); padding: 0 12px; border: 0; background: none; color: var(--ink-2);
  text-decoration: underline; text-underline-offset: 4px; cursor: pointer; font-size: 0.9rem;
}
h3 { font-size: 0.95rem; display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.list { display: grid; gap: 6px; }
.list.grid { grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); }
.item { width: 100%; height: auto; padding: 10px 12px; text-align: left; white-space: normal; justify-content: flex-start; }
.reasons { margin: 8px 0 0; padding-left: 1.2em; color: var(--ink-2); }
.chip.example { color: var(--example); background: var(--example-bg); border-color: currentColor; }
</style>
