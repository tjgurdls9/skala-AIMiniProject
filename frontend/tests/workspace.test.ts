import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeAll, describe, expect, test, vi } from 'vitest'
import App from '../src/App.vue'
import { ApiError } from '../src/api/errors'
import type { LiveApi } from '../src/api/live'
import RunWorkspace from '../src/components/RunWorkspace.vue'
import StartScreen from '../src/components/StartScreen.vue'
import { exampleSource } from '../src/examples/exampleSource'
import { findScenario } from '../src/examples/scenarios'

beforeAll(() => {
  const proto = HTMLDialogElement.prototype as HTMLDialogElement & { showModal(): void }
  if (!proto.showModal) proto.showModal = function (this: HTMLDialogElement) { this.setAttribute('open', '') }
  if (!('ResizeObserver' in globalThis)) {
    ;(globalThis as Record<string, unknown>).ResizeObserver = class { observe() {} disconnect() {} }
  }
})
afterEach(() => {
  document.body.innerHTML = ''
  sessionStorage.clear()
})

// 사건 목록은 100ms 묶음으로 화면에 반영된다(useRun EVENT_FLUSH_MS)
const flush = async () => {
  await flushPromises()
  await new Promise((r) => setTimeout(r, 120))
  await flushPromises()
}
const byText = (w: ReturnType<typeof mount>, text: string) => w.findAll('button').find((b) => b.text().includes(text))

async function workspace(id: string) {
  const w = mount(RunWorkspace, { attachTo: document.body, props: { source: exampleSource(findScenario(id)!) } })
  await flush()
  return w
}

describe('작업 공간 (합성 예시)', () => {
  test('출처·실행 상태·고정 알림·지도·장면 목록·근거·기록을 함께 보여준다', async () => {
    const w = await workspace('review-split')
    const text = w.text()
    expect(text).toContain('합성 예시 · 실제 실행 아님')
    expect(text).toContain('구현 중')
    expect(text).toContain('보안 실패 — 출시 차단')
    expect(text).toContain('작업 지도')
    expect(text).toContain('Sprint 3 · 화면·통합')
    expect(text).toContain('검증 보고서')
    expect(text).toContain('사건 기록')
    w.unmount()
  })

  test('장면 목록에서 작업을 고르면 근거 패널에 대기 이유·선행 작업·아티팩트가 나온다', async () => {
    const w = await workspace('building')
    await byText(w, '컨테이너 이미지 빌드 구성')!.trigger('click')
    await flush()
    const evidence = w.find('aside.evidence').text()
    expect(evidence).toContain('컨테이너 실행기 미연결')
    expect(evidence).toContain('할 일 조회·상태 변경 API')
    await byText(w, '합성 할 일 CSV 적재·분류 규칙')!.trigger('click')
    await flush()
    await w.find('aside.evidence').findAll('button').find((b) => b.text().includes('데이터 적재 변경'))!.trigger('click')
    await flush()
    expect(w.find('aside.evidence').text()).toContain('seed/todos.csv 적재')
    expect(w.find('aside.evidence').text()).toContain('합성 예시에는 이 산출물의 본문이 없습니다')
    w.unmount()
  })

  test('기획 아티팩트를 고르면 PlanView 본문을 보여준다', async () => {
    const w = await workspace('plan-approval')
    await w.findAll('nav.tree button').find((b) => b.text().includes('Sprint 1'))!.trigger('click')
    await flush()
    await byText(w, '요청 분석·기획안 작성')!.trigger('click')
    await flush()
    await w.find('aside.evidence').findAll('button').find((b) => b.text().includes('기획안 v1'))!.trigger('click')
    await flush()
    expect(w.find('aside.evidence').text()).toContain('저장소미설정 — 저장소 쓰기·푸시를 허용하지 않음')
    w.unmount()
  })

  test('지도에서 Sprint를 바꾸면 장면이 그 Sprint만 보여주고, 사건 기록의 작업 링크로 이동한다', async () => {
    const w = await workspace('building')
    await w.findAll('nav.tree button').find((b) => b.text().includes('Sprint 4'))!.trigger('click')
    await flush()
    expect(w.find('.roster').text()).toContain('후보 커밋 기능 검증')
    await w.find('.log').findAll('button').find((b) => b.text() === '작업 보기')!.trigger('click')
    await flush()
    expect(w.find('aside.evidence').text()).toContain('요청 분석·기획안 작성')
    w.unmount()
  })

  test('관심 분야는 강조만 하고, 강조 항목만 보기에도 승인·경고는 남는다', async () => {
    const w = await workspace('plan-approval')
    const log = () => w.find('.log')
    expect(log().find('input[type=checkbox]').attributes('disabled')).toBeDefined()
    await log().findAll('button').find((b) => b.text() === '프론트')!.trigger('click')
    await log().find('input[type=checkbox]').setValue(true)
    await flush()
    expect(log().text()).toContain('승인 요청')
    expect(log().text()).not.toContain('기획 양식·템플릿 문서 3건 검색')
    w.unmount()
  })

  test('결정 버튼과 고정 알림에서 승인·프리뷰 dialog를 연다', async () => {
    const plan = await workspace('plan-approval')
    await byText(plan, '기획 검토·승인')!.trigger('click')
    await flush()
    expect(document.querySelector('dialog[open]')?.textContent).toContain('기획 승인')
    plan.unmount()

    const preview = await workspace('preview')
    await byText(preview, '프리뷰 보기')!.trigger('click')
    await flush()
    expect(document.querySelector('dialog[open]')?.textContent).toContain('기록된 프리뷰 — 지금 실행 중인 앱이 아닙니다')
    expect(document.querySelector('dialog[open] iframe')).toBeNull()
    preview.unmount()

    const release = await workspace('release-approval')
    await byText(release, '배포 대상 검토')!.trigger('click')
    await flush()
    expect(document.querySelector('dialog[open]')?.textContent).toContain('배포 승인')
    release.unmount()
  })

  test('일시 중지는 예시에서 보내지 않았음을 알리고, 재개·취소는 확인 dialog를 거친다', async () => {
    const w = await workspace('building')
    await byText(w, '일시 중지')!.trigger('click')
    await flush()
    expect(w.text()).toContain('합성 예시에서는 명령을 보내지 않았습니다')
    await byText(w, '실행 취소')!.trigger('click')
    await flush()
    expect(document.querySelector('dialog[open]')?.textContent).toContain('이어서 진행할 수 없습니다')
    w.unmount()

    const paused = await workspace('paused')
    expect(byText(paused, '재개')).toBeTruthy()
    await byText(paused, '재개')!.trigger('click')
    await flush()
    expect(document.querySelector('dialog[open]')?.textContent).toContain('최신 명세·무료 공급자 자격')
    paused.unmount()
  })

  test('완료된 실행에는 중지 버튼이 없다', async () => {
    const w = await workspace('succeeded')
    expect(byText(w, '일시 중지')).toBeUndefined()
    expect(w.text()).toContain('완료')
    w.unmount()
  })

  test('스냅샷을 읽지 못하면 실행 상태를 바꾸지 않고 다시 시도를 제공한다', async () => {
    const source = { ...exampleSource(findScenario('building')!), getSnapshot: vi.fn().mockRejectedValue(new ApiError(404, 'NOT_FOUND', '실행을 찾을 수 없습니다.')) }
    const w = mount(RunWorkspace, { attachTo: document.body, props: { source } })
    await flush()
    expect(w.text()).toContain('실행을 불러오지 못했습니다: 실행을 찾을 수 없습니다.')
    expect(byText(w, '다시 연결')).toBeUndefined()
    w.unmount()
  })
})

function fakeApi(overrides: Partial<Record<keyof LiveApi, unknown>> = {}): LiveApi {
  return {
    connect: vi.fn(async () => {}),
    getRuntime: vi.fn(async () => ({
      protocol_version: 1, live_available: true, provider: 'ollama_local', model: 'qwen:test', model_status: 'ready',
      runner_status: 'ready', inference_slots: 1, external_api_enabled: false, deployment_enabled: false, reasons: [],
    })),
    listReplays: vi.fn(async () => [{ project_id: 'p1', title: '지난 실행', source_run_id: 'run-old', recorded_at: '2026-10-19T00:00:00Z', manifest_digest: `sha256:${'ab'.repeat(32)}` }]),
    createProject: vi.fn(async () => ({ project_id: 'p-new', title: 't', created_at: 'x' })),
    createRun: vi.fn(async () => ({ run_id: 'run-new' })),
    ...overrides,
  } as unknown as LiveApi
}

describe('시작 화면', () => {
  test('실행 가능하면 원문을 그대로 보내 프로젝트와 LIVE 실행을 만든다', async () => {
    const api = fakeApi()
    const w = mount(StartScreen, { attachTo: document.body, props: { api } })
    await flush()
    expect(w.text()).toContain('무엇을 만들까요?')
    expect(w.findAll('textarea')).toHaveLength(1)
    await w.find('textarea').setValue('문의 대시보드\n고객 문의를 분류해 주세요')
    await w.find('textarea').trigger('keydown', { key: 'Enter' })
    await flush()
    expect(api.createProject).toHaveBeenCalledWith({ title: '문의 대시보드', request: '문의 대시보드\n고객 문의를 분류해 주세요' })
    expect(api.createRun).toHaveBeenCalledWith('p-new', { mode: 'live' })
    const [[runId, origin]] = w.emitted('openRun') as Array<[string, { x: number; y: number }]>
    expect(runId).toBe('run-new')
    expect(typeof origin.x).toBe('number')
    w.unmount()
  })

  test('실제 기록 재생은 원본 실행 ID로 replay 실행을 만든다', async () => {
    const api = fakeApi()
    const w = mount(StartScreen, { attachTo: document.body, props: { api } })
    await flush()
    await byText(w, '실제 기록 재생')!.trigger('click')
    await flush()
    await byText(w, '지난 실행')!.trigger('click')
    await flush()
    expect(api.createRun).toHaveBeenCalledWith('p1', { mode: 'replay', source_run_id: 'run-old' })
    w.unmount()
  })

  test('LIVE 불가 이유를 보여주고 시작 버튼을 막는다. 서버 오류에서 예시로 자동 전환하지 않는다', async () => {
    const api = fakeApi({
      getRuntime: vi.fn(async () => ({ protocol_version: 1, live_available: false, provider: 'ollama_local', model: null, model_status: 'not_configured', runner_status: 'unavailable', inference_slots: 1, external_api_enabled: false, deployment_enabled: false, reasons: ['모델 미설정'] })),
      listReplays: vi.fn(async () => []),
    })
    const w = mount(StartScreen, { attachTo: document.body, props: { api } })
    await flush()
    expect(w.text()).toContain('지금은 LIVE 실행을 시작할 수 없습니다 — 모델 미설정')
    await w.find('textarea').setValue('무언가')
    expect(w.find('button.send').attributes('disabled')).toBeDefined()
    await w.find('textarea').trigger('keydown', { key: 'Enter' })
    await flush()
    expect(api.createProject).not.toHaveBeenCalled()
    await byText(w, '실제 기록 재생')!.trigger('click')
    await flush()
    expect(w.text()).toContain('아직 실제 기록이 없습니다')
    w.unmount()

    const down = mount(StartScreen, { attachTo: document.body, props: { api: fakeApi({ connect: vi.fn().mockRejectedValue(new ApiError(502, 'NETWORK', 'API 서버에 연결하지 못했습니다 (502)')) }) } })
    await flush()
    expect(down.text()).toContain('API 서버에 연결하지 못했습니다')
    expect(down.emitted('openExample')).toBeUndefined()
  })

  test('실행 생성 실패는 원인과 다음 행동을 보여준다', async () => {
    const api = fakeApi({ createRun: vi.fn().mockRejectedValue(new ApiError(409, 'RUNTIME_UNAVAILABLE', '실행기 없음')) })
    const w = mount(StartScreen, { attachTo: document.body, props: { api } })
    await flush()
    await w.find('textarea').setValue('r')
    await w.find('form').trigger('submit')
    await flush()
    expect(w.text()).toContain('실행기 없음')
    expect(w.text()).toContain('실행 환경이 준비되지 않았습니다')
    await byText(w, '실제 기록 재생')!.trigger('click')
    await flush()
    await byText(w, '[예시] 구현 중')!.trigger('click')
    expect((w.emitted('openExample') as unknown[][])[0][0]).toBe('building')
    w.unmount()
  })
})

describe('App 라우팅', () => {
  test('?example=로 예시 작업 공간을 열고 처음으로 돌아간다', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(null, { status: 502 })))
    window.history.replaceState(null, '', '/?example=paused')
    const w = mount(App, { attachTo: document.body })
    await flush()
    expect(w.text()).toContain('일시 중지됨')
    await byText(w, '← 처음')!.trigger('click')
    await flush()
    expect(window.location.search).toBe('')
    expect(w.text()).toContain('무엇을 만들까요?')
    window.dispatchEvent(new PopStateEvent('popstate'))
    w.unmount()
    vi.unstubAllGlobals()
  })
})
