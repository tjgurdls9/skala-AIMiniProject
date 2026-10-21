// CR-C12 공개 근거 표시 + S12 서명 없는 기록 import/export (계약 573c169 → ce6dcc1)
import Ajv2020 from 'ajv/dist/2020'
import addFormats from 'ajv-formats'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeAll, describe, expect, test, vi } from 'vitest'
import { ApiError } from '../src/api/errors'
import { LiveApi, RECORDING_MAX_BYTES } from '../src/api/live'
import type { Snapshot } from '../src/api/types'
import EvidenceBody from '../src/components/EvidenceBody.vue'
import PreviewDialog from '../src/components/PreviewDialog.vue'
import RecordingExport from '../src/components/RecordingExport.vue'
import RunWorkspace from '../src/components/RunWorkspace.vue'
import SourceBadge from '../src/components/SourceBadge.vue'
import StartScreen from '../src/components/StartScreen.vue'
import { CONTEXT_BODY, fakeDigest, RETRIEVAL_BODY } from '../src/examples/base'
import { exampleSource } from '../src/examples/exampleSource'
import { findScenario } from '../src/examples/scenarios'
import { isContextEvidence, isRetrievalEvidence, safeHttpUrl } from '../src/model/evidence'

beforeAll(() => {
  const proto = HTMLDialogElement.prototype as HTMLDialogElement & { showModal(): void }
  if (!proto.showModal) proto.showModal = function (this: HTMLDialogElement) { this.setAttribute('open', '') }
  if (!('ResizeObserver' in globalThis)) {
    ;(globalThis as Record<string, unknown>).ResizeObserver = class { observe() {} disconnect() {} }
  }
})
afterEach(() => {
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})

const flush = async () => {
  await flushPromises()
  await new Promise((r) => setTimeout(r, 120))
  await flushPromises()
}

const dir = resolve(__dirname, '../../docs/planning')
const ajv = new Ajv2020({ strict: false, allErrors: true })
addFormats(ajv)
ajv.addSchema(JSON.parse(readFileSync(resolve(dir, 'protocol.v1.schema.json'), 'utf8')), 'protocol.v1.schema.json')
ajv.addSchema(JSON.parse(readFileSync(resolve(dir, 'http.v1.schema.json'), 'utf8')), 'http.v1.schema.json')
const valid = (ref: string, v: unknown) => ajv.getSchema(ref)!(v)

describe('합성 예시 근거 본문은 계약을 따른다', () => {
  test('RetrievalEvidence·ContextEvidence 스키마에 맞고 가드도 통과한다', () => {
    expect(valid('http.v1.schema.json#/$defs/RetrievalEvidence', RETRIEVAL_BODY)).toBe(true)
    expect(valid('http.v1.schema.json#/$defs/ContextEvidence', CONTEXT_BODY)).toBe(true)
    expect(isRetrievalEvidence(RETRIEVAL_BODY)).toBe(true)
    expect(isContextEvidence(CONTEXT_BODY)).toBe(true)
  })

  test('형식이 어긋난 본문은 근거로 인정하지 않는다', () => {
    expect(isRetrievalEvidence({ ...RETRIEVAL_BODY, method: 'magic' })).toBe(false)
    expect(isRetrievalEvidence({ ...RETRIEVAL_BODY, sources: Array(6).fill(RETRIEVAL_BODY.sources[0]) })).toBe(false)
    expect(isRetrievalEvidence({ ...RETRIEVAL_BODY, sources: [{ ...RETRIEVAL_BODY.sources[0], chunk_id: 'x' }] })).toBe(false)
    expect(isContextEvidence({ ...CONTEXT_BODY, completed_fragments: 1.5 })).toBe(false)
    expect(isContextEvidence({ ...CONTEXT_BODY, source_digest: 'nope' })).toBe(false)
    expect(isRetrievalEvidence(null)).toBe(false)
    expect(isContextEvidence(null)).toBe(false)
  })

  // CT46: 스키마가 거절하는 본문은 가드도 거절해야 화면이 계약 밖 값을 조회하지 않는다(형식 검사 uri·date-time 제외)
  const src0 = RETRIEVAL_BODY.sources[0]
  const ctx0 = CONTEXT_BODY.sources[0]
  test.each([
    ['역할 원소가 계약 밖', { ...RETRIEVAL_BODY, sources: [{ ...src0, roles: ['unknown'] }] }],
    ['역할 빈 배열', { ...RETRIEVAL_BODY, sources: [{ ...src0, roles: [] }] }],
    ['역할 중복', { ...RETRIEVAL_BODY, sources: [{ ...src0, roles: ['builder', 'builder'] }] }],
    ['빈 버전', { ...RETRIEVAL_BODY, sources: [{ ...src0, version: '' }] }],
    ['빈 라이선스', { ...RETRIEVAL_BODY, sources: [{ ...src0, license: '' }] }],
    ['오류 코드 계약 밖', { ...RETRIEVAL_BODY, error_code: 'BOOM' }],
    ['출처의 추가 필드', { ...RETRIEVAL_BODY, sources: [{ ...src0, extra: 1 }] }],
    ['본문의 추가 필드', { ...RETRIEVAL_BODY, extra: 1 }],
  ])('검색 근거: %s → 스키마와 가드 모두 거절', (_, body) => {
    expect(valid('http.v1.schema.json#/$defs/RetrievalEvidence', body)).toBe(false)
    expect(isRetrievalEvidence(body)).toBe(false)
  })
  test.each([
    ['음수 위치', { ...CONTEXT_BODY, sources: [{ ...ctx0, offset: -1 }] }],
    ['길이 0', { ...CONTEXT_BODY, sources: [{ ...ctx0, length: 0 }] }],
    ['음수 조각 수', { ...CONTEXT_BODY, completed_fragments: -1 }],
    ['출처의 추가 필드', { ...CONTEXT_BODY, sources: [{ ...ctx0, extra: 1 }] }],
    ['본문의 추가 필드', { ...CONTEXT_BODY, extra: 1 }],
  ])('문맥 근거: %s → 스키마와 가드 모두 거절', (_, body) => {
    expect(valid('http.v1.schema.json#/$defs/ContextEvidence', body)).toBe(false)
    expect(isContextEvidence(body)).toBe(false)
  })

  test('출처 URL은 http(s)만 링크로 쓴다', () => {
    expect(safeHttpUrl('https://a.example/x')).toBe('https://a.example/x')
    expect(safeHttpUrl('javascript:alert(1)')).toBeNull()
    expect(safeHttpUrl('not a url')).toBeNull()
  })
})

describe('CR-C12 근거 표시', () => {
  test('의미 검색 결과는 방법·모델·출처·버전·라이선스·점수(판정 아님)를 보여 준다', () => {
    const text = mount(EvidenceBody, { props: { retrieval: RETRIEVAL_BODY as never } }).text()
    expect(text).toContain('✓ 근거 찾음')
    expect(text).toContain('의미 검색 · local-embedding-example')
    expect(text).toContain('https://docs.example.invalid/fastapi/routing')
    expect(text).toContain('버전 v0.115 · MIT')
    expect(text).toContain('관련도 0.82 (판정 아님)')
  })

  test('검색 실패는 빈 결과와 구분해 실패 원인을 보여 준다', () => {
    const failed = mount(EvidenceBody, { props: { retrieval: { ...RETRIEVAL_BODY, status: 'search_error', error_code: 'MODEL_UNAVAILABLE', sources: [] } as never } }).text()
    expect(failed).toContain('✕ 검색 실패')
    expect(failed).toContain('임베딩 모델을 쓸 수 없음')
    expect(failed).toContain('검색이 실패해 근거가 없습니다')
    const none = mount(EvidenceBody, { props: { retrieval: { ...RETRIEVAL_BODY, method: 'keyword', model: null, status: 'no_results', sources: [] } as never } }).text()
    expect(none).toContain('○ 결과 없음')
    expect(none).toContain('키워드 검색')
    expect(none).toContain('조건에 맞는 근거가 없습니다')
  })

  test('문맥 근거는 조각 수·원문 해시·위치를 보여 주고 승인 증거가 아님을 밝힌다', () => {
    const text = mount(EvidenceBody, { props: { context: CONTEXT_BODY as never } }).text()
    expect(text).toContain('✓ 문맥 준비됨')
    expect(text).toContain('조각 2 / 2')
    expect(text).toContain('위치 0–180(문자)')
    expect(text).toContain('승인 증거가 아닙니다')
    expect(mount(EvidenceBody, { props: { context: { ...CONTEXT_BODY, status: 'needs_input', completed_fragments: 1 } as never } }).text()).toContain('? 입력 필요')
  })

  test('작업 화면에서 검색 근거 아티팩트를 열면 본문이 표시된다', async () => {
    const w = mount(RunWorkspace, { attachTo: document.body, props: { source: exampleSource(findScenario('building')!) } })
    await flush()
    await w.findAll('button').find((b) => b.text().includes('문의 조회·상태 변경 API'))!.trigger('click')
    await flush()
    await w.find('aside.evidence').findAll('button').find((b) => b.text().includes('API 작업 검색 근거'))!.trigger('click')
    await flush()
    expect(w.find('aside.evidence').text()).toContain('의미 검색 · local-embedding-example')
    w.unmount()
  })

  test('형식이 맞지 않는 근거 본문은 표시하지 않고 알린다', async () => {
    const scenario = findScenario('building')!
    const source = { ...exampleSource(scenario), getArtifact: async (id: string) => (id === 'a-retrieval-api' ? { bad: true } : scenario.artifactBodies[id]) }
    const w = mount(RunWorkspace, { attachTo: document.body, props: { source } })
    await flush()
    await w.findAll('button').find((b) => b.text().includes('문의 조회·상태 변경 API'))!.trigger('click')
    await flush()
    await w.find('aside.evidence').findAll('button').find((b) => b.text().includes('API 작업 검색 근거'))!.trigger('click')
    await flush()
    expect(w.find('aside.evidence').text()).toContain('근거 본문 형식이 계약과 맞지 않아 표시하지 않습니다')
    w.unmount()
  })

  test('CT46: 역할 값이 계약 밖인 근거 본문은 렌더 오류 없이 형식 오류로 표시한다', async () => {
    const scenario = findScenario('building')!
    const bad = { ...RETRIEVAL_BODY, sources: [{ ...RETRIEVAL_BODY.sources[0], roles: ['unknown'] }] }
    const source = { ...exampleSource(scenario), getArtifact: async (id: string) => (id === 'a-retrieval-api' ? bad : scenario.artifactBodies[id]) }
    const errors = vi.spyOn(console, 'error').mockImplementation(() => {})
    const warns = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const w = mount(RunWorkspace, { attachTo: document.body, props: { source } })
    await flush()
    await w.findAll('button').find((b) => b.text().includes('문의 조회·상태 변경 API'))!.trigger('click')
    await flush()
    await w.find('aside.evidence').findAll('button').find((b) => b.text().includes('API 작업 검색 근거'))!.trigger('click')
    await flush()
    expect(w.find('aside.evidence').text()).toContain('근거 본문 형식이 계약과 맞지 않아 표시하지 않습니다')
    expect(errors).not.toHaveBeenCalled()
    expect(warns.mock.calls.flat().join(' ')).not.toMatch(/Unhandled error|render function/)
    w.unmount()
  })
})

describe('S12 기록 import/export API', () => {
  const CSRF = 'x'.repeat(40)
  const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status })
  function api() {
    const calls: Array<{ url: string; init: RequestInit }> = []
    const fn = vi.fn(async (url: string, init: RequestInit = {}) => {
      calls.push({ url, init })
      if (url === '/api/session') return json(200, { csrf_token: CSRF, expires_at: 'x' })
      if (url.endsWith('/recording')) return json(200, { format: 'lifecycle-recording', manifest_digest: fakeDigest('aa') })
      if (url === '/api/recordings/import') return json(201, { project_id: 'p', run_id: 'r-imported', manifest_digest: fakeDigest('aa'), read_only: true, provenance: 'imported_unsigned' })
      return json(404, { error: { code: 'NOT_FOUND', message: '없음' } })
    })
    return { live: new LiveApi(fn as unknown as typeof fetch), calls }
  }

  test('내보내기는 실행별 recording 경로, 가져오기는 CSRF와 함께 JSON 본문을 보낸다', async () => {
    const { live, calls } = api()
    await live.getRecording('run/1')
    expect(calls[0].url).toBe('/api/runs/run%2F1/recording')
    const result = await live.importRecording(JSON.stringify({ format: 'lifecycle-recording', version: 1, manifest_digest: 'm' }))
    expect(result.provenance).toBe('imported_unsigned')
    const post = calls.find((c) => c.url === '/api/recordings/import')!
    expect((post.init.headers as Record<string, string>)['X-CSRF-Token']).toBe(CSRF)
    expect(JSON.parse(String(post.init.body)).format).toBe('lifecycle-recording')
  })

  test('16 MiB 초과·JSON 아님·형식 다름은 보내기 전에 거절한다', async () => {
    const { live, calls } = api()
    await expect(live.importRecording('x'.repeat(RECORDING_MAX_BYTES + 1))).rejects.toMatchObject({ code: 'BODY_TOO_LARGE' })
    await expect(live.importRecording('{bad')).rejects.toMatchObject({ code: 'INVALID_COMMAND' })
    await expect(live.importRecording(JSON.stringify({ format: 'other', version: 1 }))).rejects.toMatchObject({ code: 'INVALID_COMMAND' })
    expect(calls.some((c) => c.url === '/api/recordings/import')).toBe(false)
  })
})

describe('S12 화면', () => {
  const imported: Snapshot = {
    ...findScenario('preview')!.snapshot,
    mode: 'replay',
    replay_source: { source_run_id: 'ae947cc5946f425e9ec16239c16d85e7', recorded_at: '2026-10-20T12:10:00Z', manifest_digest: fakeDigest('ab'), provenance: 'imported_unsigned' },
  }

  test('가져온 기록은 로컬 원장 재생·LIVE와 다른 배지와 서명 없음 안내를 보인다', () => {
    const text = mount(SourceBadge, { props: { kind: 'live', snapshot: imported } }).text()
    expect(text).toContain('가져온 기록(서명 없음) · 읽기 전용')
    expect(text).toContain('해시는 훼손 검출용이며 출처 서명이 아님')
    const local = mount(SourceBadge, { props: { kind: 'live', snapshot: { ...imported, replay_source: { ...imported.replay_source!, provenance: 'local_ledger' } } } }).text()
    expect(local).toContain('실제 기록 재생 · 읽기 전용')
    expect(local).not.toContain('서명')
  })

  test('가져온 기록에서는 프리뷰 iframe을 열지 않는다', async () => {
    const w = mount(PreviewDialog, {
      attachTo: document.body,
      props: { open: true, snapshot: imported, source: { ...exampleSource(findScenario('preview')!), kind: 'live' }, readOnly: true, selectedArtifactId: null, send: vi.fn() },
    })
    await flush()
    expect(w.find('iframe').exists()).toBe(false)
    expect(w.text()).toContain('가져온 기록(서명 없음)에서는 외부 앱을 열지 않습니다')
    w.unmount()
  })

  test('기록 내보내기는 JSON 파일을 받게 하고, 합성 예시는 내보내지 않는다', async () => {
    const create = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:x')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const source = { ...exampleSource(findScenario('preview')!), kind: 'live' as const, getRecording: vi.fn(async () => ({ manifest_digest: fakeDigest('ab') }) as never) }
    const w = mount(RecordingExport, { props: { source, runId: 'run-12345678901234' } })
    await w.find('button').trigger('click')
    await flush()
    expect(create).toHaveBeenCalledOnce()
    expect(click).toHaveBeenCalledOnce()
    expect(w.text()).toContain('내보냄 · manifest')
    // 실제 b7f01f0 bundle에 변경 요청 원문·명세 본문이 들어 있었다. 사용자 입력이 없다고 안내하면 안 된다
    expect(w.text()).not.toContain('원문 요청')
    expect(w.text()).toContain('사용자 입력과 산출물이 들어 있을 수 있으니 공유 전에 내용을 확인하세요')
    const example = mount(RecordingExport, { props: { source: exampleSource(findScenario('preview')!), runId: 'r' } })
    expect(example.find('button').exists()).toBe(false)
    expect(example.text()).toContain('합성 예시는 실제 기록이 아니어서 내보내지 않습니다')
  })

  test('내보내기 실패는 원인을 보여 준다', async () => {
    const source = { ...exampleSource(findScenario('preview')!), kind: 'live' as const, getRecording: vi.fn().mockRejectedValue(new ApiError(422, 'INVALID_COMMAND', '비밀 형식이 검출돼 내보내지 않습니다')) }
    const w = mount(RecordingExport, { props: { source, runId: 'r' } })
    await w.find('button').trigger('click')
    await flush()
    expect(w.text()).toContain('비밀 형식이 검출돼 내보내지 않습니다')
  })

  test('시작 화면에서 기록 파일을 가져오면 읽기 전용 실행으로 연다', async () => {
    const importRecording = vi.fn(async () => ({ project_id: 'p', run_id: 'r-imported', manifest_digest: fakeDigest('aa'), read_only: true, provenance: 'imported_unsigned' }))
    const fakeApi = {
      connect: vi.fn(async () => {}),
      getRuntime: vi.fn(async () => ({ protocol_version: 1, live_available: false, provider: 'ollama_local', model: null, model_status: 'not_configured', runner_status: 'unavailable', inference_slots: 1, external_api_enabled: false, deployment_enabled: false, reasons: ['모델 미설정'] })),
      listReplays: vi.fn(async () => [{ project_id: 'p', title: '가져온 실행', source_run_id: 'r0', recorded_at: '2026-10-20T00:00:00Z', manifest_digest: fakeDigest('aa'), provenance: 'imported_unsigned' }]),
      importRecording,
    } as unknown as LiveApi
    const w = mount(StartScreen, { attachTo: document.body, props: { api: fakeApi } })
    await flush()
    await w.find('button.more').trigger('click')
    await flush()
    expect(w.text()).toContain('가져온 기록 · 서명 없음')
    const input = w.find('input[type=file]').element as HTMLInputElement
    const file = new File(['{"format":"lifecycle-recording","version":1}'], 'recording.json', { type: 'application/json' })
    Object.defineProperty(input, 'files', { value: [file], configurable: true })
    await w.find('input[type=file]').trigger('change')
    await flush()
    expect(importRecording).toHaveBeenCalledWith('{"format":"lifecycle-recording","version":1}')
    expect((w.emitted('openRun') as unknown[][])[0][0]).toBe('r-imported')

    importRecording.mockRejectedValueOnce(new ApiError(422, 'INVALID_COMMAND', '해시가 맞지 않습니다'))
    await w.find('button.more').trigger('click')
    await flush()
    Object.defineProperty(w.find('input[type=file]').element, 'files', { value: [file], configurable: true })
    await w.find('input[type=file]').trigger('change')
    await flush()
    expect(w.text()).toContain('해시가 맞지 않습니다')
    // 통합본 실제 422 INVALID_COMMAND에 "잠시 후 다시 시도"가 붙었다. 같은 내용 재시도는 결과가 같다
    expect(w.text()).not.toContain('잠시 후 다시 시도하세요')
    expect(w.text()).toContain('같은 내용으로 다시 보내도 결과는 같습니다')
    w.unmount()
  })
})

describe('작업에 묶이지 않은 실행 근거 (실제 S09 LIVE 846eed64: 기획 단계 근거, 작업 0개)', () => {
  // 실제 서버 본문과 같은 모양: planner 의미 검색(project:// 출처), 미완료 문맥(spec 없음)
  const realRetrieval = {
    method: 'semantic', model: `qwen3-embedding:0.6b@${fakeDigest('ac')}`, role: 'planner', status: 'found',
    sources: [{ chunk_id: fakeDigest('91'), collected_at: '2026-10-21T00:39:48.189827+00:00', content_digest: fakeDigest('ef'), license: 'project-local', roles: ['planner', 'builder', 'validator', 'security'], score: 0.47695513870498535, url: 'project://contracts/v1', version: `v1@${fakeDigest('73')}` }],
  }
  const realContext = {
    completed_fragments: 0, total_fragments: 2, status: 'needs_input', spec_version_id: null, source_digest: fakeDigest('bb'),
    sources: [{ request_id: '7df94f096d6a49eea3e987a2ba93d7ac', content_digest: fakeDigest('94'), offset: 0, length: 108 }],
  }
  const base = findScenario('failed')!
  const snapshot: Snapshot = {
    ...base.snapshot, state: 'needs_input', spec_version_id: null, phases: [], sprints: [], tasks: [], approvals: [], reports: [],
    artifacts: [
      { id: 'a-ctx-live', kind: 'context', title: '문맥 준비 근거', public_summary: '문맥 준비 근거', content_digest: fakeDigest('c3') },
      { id: 'a-ret-live', kind: 'retrieval', title: '역할별 검색 근거', public_summary: '역할별 검색 근거', content_digest: fakeDigest('c4') },
    ],
  }
  const bodies: Record<string, unknown> = { 'a-ctx-live': realContext, 'a-ret-live': realRetrieval }

  test('실제와 같은 모양의 본문이 스키마와 가드를 통과한다', () => {
    expect(valid('http.v1.schema.json#/$defs/RetrievalEvidence', realRetrieval)).toBe(true)
    expect(valid('http.v1.schema.json#/$defs/ContextEvidence', realContext)).toBe(true)
    expect(isRetrievalEvidence(realRetrieval)).toBe(true)
    expect(isContextEvidence(realContext)).toBe(true)
  })

  test('작업이 없어도 실행 근거로 나열하고, 열면 본문을 보여 준다(project:// 출처는 링크로 만들지 않음)', async () => {
    const source = { ...exampleSource(base), kind: 'live' as const, getSnapshot: async () => snapshot, getArtifact: async (id: string) => bodies[id] }
    const w = mount(RunWorkspace, { attachTo: document.body, props: { source } })
    await flush()
    const region = w.find('aside.evidence section[aria-label="실행 근거"]')
    expect(region.exists()).toBe(true)
    expect(region.text()).toContain('역할별 검색 근거')
    expect(region.text()).toContain('문맥 준비 근거')
    await region.findAll('button').find((b) => b.text().includes('역할별 검색 근거'))!.trigger('click')
    await flush()
    const panel = w.find('aside.evidence').text()
    expect(panel).toContain('의미 검색')
    expect(panel).toContain('project://contracts/v1')
    expect(w.find('aside.evidence a[href^="project:"]').exists()).toBe(false)
    w.unmount()
  })

  test('작업에 연결된 근거는 실행 근거에 다시 나열하지 않는다', async () => {
    const w = mount(RunWorkspace, { attachTo: document.body, props: { source: exampleSource(findScenario('building')!) } })
    await flush()
    expect(w.find('aside.evidence section[aria-label="실행 근거"]').exists()).toBe(false)
    w.unmount()
  })
})
