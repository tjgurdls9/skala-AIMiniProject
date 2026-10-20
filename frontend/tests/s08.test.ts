// DEV-S08 사용자 디자인 지시 구현: 빈 화면 입력 → 전환 → 전체 화면 사무실 → 스크롤 축소
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeAll, describe, expect, test, vi } from 'vitest'
import App from '../src/App.vue'
import type { LiveApi } from '../src/api/live'
import RunWorkspace from '../src/components/RunWorkspace.vue'
import SceneRoster from '../src/components/SceneRoster.vue'
import StartScreen from '../src/components/StartScreen.vue'
import { exampleSource } from '../src/examples/exampleSource'
import { findScenario } from '../src/examples/scenarios'
import { titleFrom } from '../src/model/prompt'

beforeAll(() => {
  const proto = HTMLDialogElement.prototype as HTMLDialogElement & { showModal(): void }
  if (!proto.showModal) proto.showModal = function (this: HTMLDialogElement) { this.setAttribute('open', '') }
  if (!('ResizeObserver' in globalThis)) {
    ;(globalThis as Record<string, unknown>).ResizeObserver = class { observe() {} disconnect() {} }
  }
})
afterEach(() => {
  document.body.innerHTML = ''
  vi.unstubAllGlobals()
  window.history.replaceState(null, '', '/')
  window.scrollTo(0, 0)
})

const flush = async () => {
  await flushPromises()
  await new Promise((r) => setTimeout(r, 120))
  await flushPromises()
}

function api(): LiveApi {
  return {
    connect: vi.fn(async () => {}),
    getRuntime: vi.fn(async () => ({ protocol_version: 1, live_available: true, provider: 'ollama_local', model: 'q', model_status: 'ready', runner_status: 'ready', inference_slots: 1, external_api_enabled: false, deployment_enabled: false, reasons: [] })),
    listReplays: vi.fn(async () => []),
    createProject: vi.fn(async () => ({ project_id: 'p', title: 't', created_at: 'x' })),
    createRun: vi.fn(async () => ({ run_id: 'r' })),
  } as unknown as LiveApi
}

describe('시작 화면: 굵은 문구 하나 + 입력창 하나', () => {
  test('제목은 원문 첫 줄에서 만들고 길면 줄인다', () => {
    expect(titleFrom('  대시보드  \n세부 설명')).toBe('대시보드')
    expect(titleFrom('가'.repeat(80))).toHaveLength(60)
  })

  test('Shift+Enter와 한글 조합 중 Enter는 보내지 않는다', async () => {
    const a = api()
    const w = mount(StartScreen, { attachTo: document.body, props: { api: a } })
    await flush()
    await w.find('textarea').setValue('문의 앱')
    await w.find('textarea').trigger('keydown', { key: 'Enter', shiftKey: true })
    await w.find('textarea').trigger('keydown', { key: 'Enter', isComposing: true })
    await flush()
    expect(a.createProject).not.toHaveBeenCalled()
    expect(w.findAll('h1')).toHaveLength(1)
    w.unmount()
  })
})

describe('팟 전환', () => {
  test('View Transitions가 있으면 입력 위치에서 원형으로 열고, 없으면 바로 바꾼다', async () => {
    const animate = vi.fn()
    document.documentElement.animate = animate as unknown as typeof document.documentElement.animate
    const start = vi.fn((cb: () => Promise<void>) => {
      void cb()
      return { ready: Promise.resolve() }
    })
    ;(document as unknown as { startViewTransition: typeof start }).startViewTransition = start
    vi.stubGlobal('fetch', vi.fn(async () => new Response(null, { status: 502 })))
    const w = mount(App, { attachTo: document.body })
    await flush()
    await w.find('button.more').trigger('click')
    await flush()
    await w.findAll('button').find((b) => b.text().includes('[예시] 구현 중'))!.trigger('click', { clientX: 100, clientY: 200 })
    await flush()
    expect(start).toHaveBeenCalledOnce()
    expect(window.location.search).toBe('?example=building')
    const [keyframes, options] = animate.mock.calls[0]
    expect(keyframes.clipPath[0]).toBe('circle(0px at 100px 200px)')
    expect(options.pseudoElement).toBe('::view-transition-new(root)')
    // 처음으로는 원점 없이 바로 바뀐다
    await w.findAll('button').find((b) => b.text().includes('처음'))!.trigger('click')
    await flush()
    expect(start).toHaveBeenCalledOnce()
    delete (document as unknown as { startViewTransition?: unknown }).startViewTransition
    w.unmount()
  })
})

describe('전체 화면 사무실 → 스크롤 축소', () => {
  test('스크롤 진행도에 따라 --p가 0→1로 바뀌고, 축소되면 사무실 위 칩을 숨긴다', async () => {
    const w = mount(RunWorkspace, { attachTo: document.body, props: { source: exampleSource(findScenario('review-split')!) } })
    await flush()
    const root = () => (w.element as HTMLElement).style
    expect(root().getPropertyValue('--p')).toBe('0.000')
    expect(w.find('.scene-hud').text()).toContain('보안 점검 실패')
    Object.defineProperty(window, 'scrollY', { value: window.innerHeight, configurable: true })
    window.dispatchEvent(new Event('scroll'))
    await new Promise((r) => setTimeout(r, 50))
    await flushPromises()
    expect(root().getPropertyValue('--p')).toBe('1.000')
    expect(w.find('.scene-hud').classes()).toContain('gone')
    expect(w.find('.scene-hud').attributes('aria-hidden')).toBe('true')
    Object.defineProperty(window, 'scrollY', { value: 0, configurable: true })
    w.unmount()
  })

  test('사무실 위 알림 칩은 결정·문제만, 최대 3개를 고정 순서로 보이고 누르면 해당 동작을 연다', async () => {
    const w = mount(RunWorkspace, { attachTo: document.body, props: { source: exampleSource(findScenario('plan-approval')!) } })
    await flush()
    const chip = w.findAll('.hud-chip.alert')
    expect(chip).toHaveLength(1)
    await chip[0].trigger('click')
    await flush()
    expect(document.querySelector('dialog[open]')?.textContent).toContain('기획 승인')
    w.unmount()
  })

  test('상세 작업 정보 버튼은 축소 지점까지 스크롤한다', async () => {
    const scrollTo = vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
    const w = mount(RunWorkspace, { attachTo: document.body, props: { source: exampleSource(findScenario('building')!) } })
    await flush()
    await w.find('.scroll-cue').trigger('click')
    expect(scrollTo).toHaveBeenCalledWith(expect.objectContaining({ top: Math.round(window.innerHeight * 0.55) }))
    scrollTo.mockRestore()
    w.unmount()
  })
})

describe('장면과 같은 DOM 좌석 목록', () => {
  test('구역별로 작업을 보여주고 선택을 알린다', async () => {
    const tasks = findScenario('building')!.snapshot.tasks.filter((t) => t.sprint_id === 'sp-2')
    const w = mount(SceneRoster, { props: { tasks, selectedTaskId: 't-api' } })
    expect(w.text()).toContain('구현 구역')
    expect(w.find('[aria-pressed="true"]').text()).toContain('문의 조회·상태 변경 API')
    await w.findAll('button.seat')[0].trigger('click')
    expect(w.emitted('select')).toEqual([['t-contract']])
  })
})
