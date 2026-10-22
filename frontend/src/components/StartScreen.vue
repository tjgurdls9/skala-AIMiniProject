<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { ApiError, errorHint } from '../api/errors'
import type { LiveApi } from '../api/live'
import type { ReplayRecording, Runtime } from '../api/types'
import { FULL_CYCLE_BADGE, FULL_CYCLE_ID } from '../examples/fullCycle'
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
const importing = ref(false)
const importError = ref<ApiError | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const field = ref<HTMLTextAreaElement | null>(null)
/** 프로젝트는 만들었는데 실행 생성이 실패한 경우, 재시도에서 같은 프로젝트를 다시 쓴다(중복 생성 방지) */
const createdProject = ref<{ key: string; id: string } | null>(null)

const MODEL_STATUS: Record<Runtime['model_status'], string> = { not_configured: '미설정', unavailable: '연결 안 됨', ready: '준비됨' }
const RUNNER_STATUS: Record<Runtime['runner_status'], string> = { unavailable: '연결 안 됨', ready: '준비됨' }
const DATA_SOURCE: Record<NonNullable<Runtime['data_source_status']>, string> = { not_required: '필요 없음', unconfigured: '미설정 — 외부 데이터가 필요한 기능은 동작하지 않음' }

/**
 * Runtime 템플릿 보조 정보(계약 a6eb8a4). 운영자 기본값일 뿐 실행별 지원 공백(CR-C14 PlanView.support)을 대신하지 않는다.
 * 사무실은 어떤 요청이든 받는 공통 화면이라 과제 이름·기능을 지어내지 않는다. 템플릿은 서버 ID 그대로, 사유는 서버 reasons 그대로 보인다.
 * 외부 데이터가 미설정이면 LIVE 가능이 기능 가능으로 읽히지 않게 입력 아래에 알린다.
 */
const dataNotice = computed<string | null>(() => {
  const rt = runtime.value
  if (!rt || rt.data_source_status !== 'unconfigured') return null
  // LIVE 불가면 첫 사유는 입력 아래(blocked)에 이미 보이므로 나머지만 붙인다
  const rest = rt.live_available ? rt.reasons : rt.reasons.slice(1)
  const reasons = rest.length ? ` ${rest.join(' ')}` : ''
  return `외부 데이터 미설정 — 외부 데이터가 필요한 기능은 동작하지 않습니다. LIVE 가능은 로컬 모델·실행기 준비만 뜻합니다. 요청별 지원 공백은 기획 승인 화면에서 확인하세요.${reasons}`
})

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
    moreOpen.value = false // 최상위 층 dialog가 전환 위에 남지 않게
    emit('openRun', snapshot.run_id, { x: e.clientX, y: e.clientY })
  } catch (error) {
    submitError.value = error instanceof ApiError ? error : new ApiError(0, 'NETWORK', '재생을 만들지 못했습니다.')
  } finally {
    submitting.value = false
  }
}

/** 서명 없는 기록 파일 가져오기. 같은 manifest면 같은 읽기 전용 실행을 연다 */
async function importFile(): Promise<void> {
  const file = fileInput.value?.files?.[0]
  if (!file || importing.value) return
  importing.value = true
  importError.value = null
  try {
    const result = await props.api.importRecording(await file.text())
    moreOpen.value = false
    const r = fileInput.value?.getBoundingClientRect()
    emit('openRun', result.run_id, r ? { x: r.left + r.width / 2, y: r.top + r.height / 2 } : { x: window.innerWidth / 2, y: window.innerHeight / 2 })
  } catch (error) {
    importError.value = error instanceof ApiError ? error : new ApiError(0, 'NETWORK', '기록을 가져오지 못했습니다.')
  } finally {
    importing.value = false
    if (fileInput.value) fileInput.value.value = ''
  }
}

function openExample(id: string, e: MouseEvent): void {
  moreOpen.value = false // 최상위 층 dialog가 전환 위에 남지 않게
  emit('openExample', id, { x: e.clientX, y: e.clientY })
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
          placeholder="예: 팀 할 일 분류 대시보드"
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
      <p v-if="dataNotice" class="hint warn" data-testid="data-notice">{{ dataNotice }}</p>
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
          <template v-if="runtime.template_id"><dt>템플릿</dt><dd><code>{{ runtime.template_id }}</code> <span class="muted small">(운영자 기본값)</span></dd></template>
          <template v-if="runtime.data_source_status"><dt>외부 데이터</dt><dd :class="{ 'tone-warn': runtime.data_source_status === 'unconfigured' }">{{ DATA_SOURCE[runtime.data_source_status] }}</dd></template>
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
              <span>
                <strong>{{ r.title }}</strong>
                <span v-if="r.provenance === 'imported_unsigned'" class="chip">가져온 기록 · 서명 없음</span>
                <br /><span class="small muted">{{ formatTime(r.recorded_at) }} · manifest <code>{{ shortDigest(r.manifest_digest) }}</code></span>
              </span>
            </button>
          </li>
        </ul>
        <p v-else-if="replays" class="muted">아직 실제 기록이 없습니다.</p>
        <p v-else class="muted">서버 연결 후 표시됩니다.</p>
      </section>
      <section aria-labelledby="import-title">
        <h3 id="import-title">기록 파일 가져오기 <span class="chip">서명 없음 · 읽기 전용</span></h3>
        <p class="small muted">다른 환경에서 내보낸 기록(JSON, 최대 16 MiB)을 읽기 전용으로 엽니다. 해시는 훼손 검출용이며 출처를 보증하지 않습니다. 승인·실행·프리뷰는 열리지 않습니다.</p>
        <label class="file">
          <span class="sr-only">기록 파일 선택</span>
          <input ref="fileInput" type="file" accept="application/json,.json" :disabled="importing" @change="importFile" />
        </label>
        <p v-if="importing" class="small muted">가져오는 중…</p>
        <div v-if="importError" class="error-box small" role="alert">{{ importError.message }} <p>{{ errorHint(importError) }}</p></div>
      </section>
      <section aria-labelledby="demo-title">
        <h3 id="demo-title">전체 과정 시연 <span class="chip example">{{ FULL_CYCLE_BADGE }}</span></h3>
        <p class="small muted">요청부터 기획 승인, 층별 구현, 검증·보안, 프리뷰, 사람 확인, 배포 승인 대상까지 합성 데이터로 한 번 돕니다. 승인 지점에서는 멈추고, 승인 버튼을 눌러야 이어집니다. 서버로는 아무것도 보내지 않습니다.</p>
        <button type="button" class="btn primary" @click="openExample(FULL_CYCLE_ID, $event)">전체 과정 시연 시작</button>
      </section>
      <section aria-labelledby="ex-title">
        <h3 id="ex-title">합성 예시 <span class="chip example">실제 실행 아님</span></h3>
        <ul class="plain list grid">
          <li v-for="s in SCENARIOS" :key="s.id">
            <button type="button" class="btn item" @click="openExample(s.id, $event)">
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
.center { width: min(720px, 100%); display: grid; gap: 16px; justify-items: center; text-align: center; }
.headline {
  font-size: clamp(2.4rem, 1.2rem + 6vw, 5.5rem);
  font-weight: 900;
  letter-spacing: -0.045em;
  line-height: 1.02;
}
.prompt {
  width: 100%;
  display: flex; align-items: flex-end; gap: 8px;
  padding: 8px 8px 8px 18px;
  border: 2px solid var(--ink); border-radius: 18px;
  background: var(--surface);
}
.prompt:focus-within { outline: 3px solid var(--focus); outline-offset: 2px; }
.prompt textarea {
  flex: 1; min-width: 0; min-height: 44px; max-height: 220px; padding: 10px 0; border: 0; background: none; resize: none;
  font-size: 1.1rem; line-height: 1.5;
}
.prompt textarea::placeholder { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.prompt textarea:focus { outline: none; }
.send {
  width: 48px; height: 48px; flex: none; border-radius: 12px; border: 0;
  background: var(--ink); color: var(--bg); font-size: 1.3rem; font-weight: 800; cursor: pointer;
}
.send:disabled { opacity: 0.3; cursor: not-allowed; }
.hint { color: var(--ink-3); font-size: 0.875rem; max-width: 600px; }
.hint.warn { color: var(--tone-warn); }
.more {
  min-height: var(--tap); padding: 0 12px; border: 0; background: none; color: var(--ink-2);
  text-decoration: underline; text-underline-offset: 4px; cursor: pointer; font-size: 0.875rem;
}
h3 { font-size: 0.95rem; display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.list { display: grid; gap: 6px; }
.list.grid { grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); }
.item { width: 100%; height: auto; padding: 10px 12px; text-align: left; white-space: normal; justify-content: flex-start; }
.reasons { margin: 8px 0 0; padding-left: 1.2em; color: var(--ink-2); }
.file input { min-height: var(--tap); font-size: 0.9rem; }
.chip.example { color: var(--example); background: var(--example-bg); border-color: currentColor; }
@media (max-width: 480px) {
  .hint { font-size: 0.8rem; }
}
</style>
