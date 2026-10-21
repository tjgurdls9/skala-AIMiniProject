// DEV-S08 사용자 디자인 지시 구현: 빈 화면 입력 → 전환 → 건물형 사무실(층 = Sprint)
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeAll, describe, expect, test, vi } from 'vitest'
import App from '../src/App.vue'
import type { LiveApi } from '../src/api/live'
import RunWorkspace from '../src/components/RunWorkspace.vue'
import SceneRoster from '../src/components/SceneRoster.vue'
import StartScreen from '../src/components/StartScreen.vue'
import type { RunSource, StreamHandlers } from '../src/api/source'
import type { Snapshot } from '../src/api/types'
import { DOORS_MS, rideTime } from '../src/composables/useElevator'
import { buildEvents } from '../src/examples/base'
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

describe('팟 전환(빛 고리 어둠)', () => {
  test('입력 위치에서 어둠이 화면을 삼킨 뒤 바꾸고, 어둠을 걷어 낸다', async () => {
    const calls: Array<{ el: Element; frames: Keyframe[] }> = []
    const original = Element.prototype.animate
    Element.prototype.animate = function (this: Element, frames: Keyframe[] | PropertyIndexedKeyframes | null) {
      calls.push({ el: this, frames: frames as Keyframe[] })
      return { finished: Promise.resolve() } as unknown as Animation
    }
    vi.stubGlobal('fetch', vi.fn(async () => new Response(null, { status: 502 })))
    const w = mount(App, { attachTo: document.body })
    await flush()
    await w.find('button.more').trigger('click')
    await flush()
    await w.findAll('button').find((b) => b.text().includes('[예시] 구현 중'))!.trigger('click', { clientX: 100, clientY: 200 })
    await flush()
    expect(window.location.search).toBe('?example=building')
    const warp = calls.find((c) => (c.el as HTMLElement).classList.contains('warp'))!
    expect((warp.el as HTMLElement).style.left).toBe('100px')
    expect(String(warp.frames[0].transform)).toContain('scale(0.001)')
    expect(document.querySelector('.warp')).toBeNull() // 끝나면 제거
    expect(document.documentElement.classList.contains('warping')).toBe(false)
    expect(document.querySelector('dialog[open]')).toBeNull() // 다른 방법 dialog가 전환 위에 남지 않음
    // 처음으로는 원점 없이 바로 바뀐다
    const before = calls.length
    await w.findAll('button').find((b) => b.text().includes('처음'))!.trigger('click')
    await flush()
    expect(calls.length).toBe(before)
    Element.prototype.animate = original
    w.unmount()
  })
})

describe('건물형 사무실: 현재 층 단면이 화면 전체, 왼쪽 엘리베이터', () => {
  async function open(id: string) {
    const w = mount(RunWorkspace, { attachTo: document.body, props: { source: exampleSource(findScenario(id)!) } })
    await flush()
    return w
  }
  const rail = (w: ReturnType<typeof mount>, text: string) => w.findAll('nav.building-rail a.rail-floor').find((a) => a.attributes('aria-label')!.includes(text))!

  test('처음에는 현재 Sprint 층 단면 하나가 화면 전체를 채우고(--p=0) 다른 층은 그리지 않는다', async () => {
    const w = await open('building')
    expect((w.element as HTMLElement).style.getPropertyValue('--p')).toBe('0.000')
    expect(w.findAll('.scene-cell .stage')).toHaveLength(1)
    expect(w.find('.floor-title').text()).toContain('2F')
    expect(w.find('.floor-title').text()).toContain('Sprint 2')
    const tasks = findScenario('building')!.snapshot.tasks.filter((t) => t.sprint_id === 'sp-2')
    expect(w.findAll('.scene-cell button.person')).toHaveLength(tasks.length)
    w.unmount()
  })

  test('엘리베이터는 층 수에 맞는 간결한 높이이고, 층 번호 위주로 위층부터 나열한다', async () => {
    const w = await open('building')
    const sprints = findScenario('building')!.snapshot.sprints
    const rows = w.findAll('nav.building-rail a.rail-floor')
    expect(rows.map((a) => a.find('.floor-num').text())).toEqual(sprints.map((_, i) => `${sprints.length - i}F`))
    expect(rows[0].attributes('aria-label')).toContain(sprints[sprints.length - 1].title)
    expect(w.find('nav.building-rail .name').exists()).toBe(false) // 이름은 접근 가능한 이름·툴팁으로만(가로로 넓히지 않는다)
    expect(w.find('nav.building-rail a[aria-current="true"]').attributes('aria-label')).toContain('Sprint 2')
    expect(w.find('nav.building-rail').element.closest('.scene-cell')).not.toBeNull()
    w.unmount()
  })

  test('층 버튼을 누르면 문이 닫히고 칸이 움직인 뒤 문이 열리면서 그 층 화면으로 바뀐다', async () => {
    const w = await open('building')
    expect(w.find('.scene-cell .elevator').classes()).toContain('open')
    expect(w.find('.elevator-display').text()).toContain('2F')
    await rail(w, 'Sprint 4').trigger('click')
    await flushPromises()
    expect(w.find('.scene-cell .elevator').classes()).not.toContain('open') // 문 닫힘
    expect(w.find('.floor-title').text()).toContain('Sprint 2') // 아직 이전 층
    await new Promise((r) => setTimeout(r, DOORS_MS + 120))
    expect(w.find('.elevator-display').text()).toContain('4F')
    expect(w.find('.elevator-display').text()).toContain('▲')
    expect(w.find('.cab').attributes('style')).toContain('--stop: 1')
    await new Promise((r) => setTimeout(r, rideTime(2) + 80))
    expect(w.find('.floor-title').text()).toContain('Sprint 4') // 문이 열리며 그 층으로
    await new Promise((r) => setTimeout(r, DOORS_MS + 80))
    expect(w.find('.scene-cell .elevator').classes()).toContain('open')
    w.unmount()
  })

  test('모션 감소 설정이면 애니메이션 없이 바로 그 층으로 바뀐다', async () => {
    vi.stubGlobal('matchMedia', (query: string) => ({ matches: query.includes('reduce'), addEventListener() {}, removeEventListener() {}, media: query }))
    const w = await open('building')
    await rail(w, 'Sprint 4').trigger('click')
    await flushPromises()
    expect(w.find('.floor-title').text()).toContain('Sprint 4')
    expect(w.find('.scene-cell .elevator').classes()).toContain('open')
    w.unmount()
  })

  test('층의 사람을 누르면 근거 패널이 그 작업을 열고, 그 층을 엘리베이터 선택으로 맞춘다', async () => {
    const w = await open('building')
    const person = w.findAll('button.person').find((b) => b.attributes('aria-label')!.includes('할 일 조회·상태 변경 API'))!
    await person.trigger('click')
    await flush()
    expect(w.find('aside.evidence').text()).toContain('할 일 조회·상태 변경 API')
    w.unmount()
  })

  test('우상단에 결정·문제 알림 칩이 고정 순서로 있고, 누르면 해당 동작을 연다', async () => {
    const w = await open('plan-approval')
    const chips = w.findAll('.scene-alerts button.alert-chip')
    expect(chips).toHaveLength(1)
    await chips[0].trigger('click')
    await flush()
    expect(document.querySelector('dialog[open]')?.textContent).toContain('기획 승인')
    w.unmount()
  })

  test('사람의 결정 대기는 보이는 현재 Sprint 층에 점선 실루엣으로 보인다', async () => {
    const w = await open('plan-approval')
    expect(w.findAll('.ghost')).toHaveLength(1)
    expect(w.find('.ghost').text()).toContain('답 기다림 · 기획 승인')
    w.unmount()
  })
})

describe('전체 화면 사무실 → 저항 있는 스크롤 축소', () => {
  test('스크롤 진행도에 따라 --p가 0→1로 바뀌고, 축소되면 사무실 위 칩을 숨긴다', async () => {
    const w = mount(RunWorkspace, { attachTo: document.body, props: { source: exampleSource(findScenario('review-split')!) } })
    await flush()
    const root = () => (w.element as HTMLElement).style
    expect(root().getPropertyValue('--p')).toBe('0.000')
    expect(w.find('.scene-alerts').text()).toContain('보안 점검 실패')
    Object.defineProperty(window, 'scrollY', { value: window.innerHeight, configurable: true })
    window.dispatchEvent(new Event('scroll'))
    await new Promise((r) => setTimeout(r, 50))
    await flushPromises()
    expect(root().getPropertyValue('--p')).toBe('1.000')
    expect(w.find('.scene-alerts').classes()).toContain('gone')
    expect(w.find('.scene-alerts').attributes('aria-hidden')).toBe('true')
    Object.defineProperty(window, 'scrollY', { value: 0, configurable: true })
    w.unmount()
  })

  test('상세 작업 정보 버튼은 저항 없이 바로 상세로 전환한다', async () => {
    const scrollTo = vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
    const w = mount(RunWorkspace, { attachTo: document.body, props: { source: exampleSource(findScenario('building')!) } })
    await flush()
    await w.find('.scroll-cue').trigger('click')
    await new Promise((r) => setTimeout(r, 600))
    const last = scrollTo.mock.calls.at(-1) as unknown as [number, number]
    expect(last[1]).toBe(Math.round(window.innerHeight * 0.55))
    scrollTo.mockRestore()
    w.unmount()
  })
})

describe('현재 Sprint 변화: 직접 고른 적이 없을 때만 엘리베이터가 따라간다', () => {
  const first = findScenario('building')!.snapshot
  /** sp-2를 모두 끝내고 sp-3을 진행 중으로 바꾼 다음 스냅샷(현재 Sprint = sp-3) */
  const next = (): Snapshot => ({
    ...first,
    last_event_seq: first.last_event_seq + 1,
    tasks: first.tasks.map((t) => (t.sprint_id === 'sp-2' ? { ...t, state: 'succeeded' as const } : t.id === 't-ui' ? { ...t, state: 'running' as const } : t)),
  })

  async function live() {
    const second = next()
    const snaps = [first, second]
    const streams: Array<{ h: StreamHandlers }> = []
    const base = exampleSource(findScenario('building')!)
    const source: RunSource = {
      ...base,
      kind: 'live',
      getSnapshot: vi.fn(async () => snaps.shift() ?? second),
      openEvents: vi.fn((_after: number, h: StreamHandlers) => {
        streams.push({ h })
        return () => {}
      }),
    }
    vi.stubGlobal('matchMedia', (query: string) => ({ matches: query.includes('reduce'), addEventListener() {}, removeEventListener() {}, media: query }))
    const w = mount(RunWorkspace, { attachTo: document.body, props: { source } })
    await flush()
    // 스냅샷까지의 기록 사건을 먼저 받아 누락 경로를 타지 않게 한다
    buildEvents(Array.from({ length: first.last_event_seq }, () => ['tool_finished', 'h', {}] as never), 1, 0).forEach((e) => streams.at(-1)!.h.onEvent({ ...e, state_version: first.state_version }))
    await flushPromises()
    const advance = async () => {
      streams.at(-1)!.h.onEvent({ ...buildEvents([['task_started', 'x', { task_id: 't-ui' }]], first.last_event_seq + 1, first.state_version)[0], state_version: first.state_version })
      await flush()
    }
    return { w, advance }
  }

  test('직접 고른 적이 없으면 현재 Sprint가 바뀔 때 그 층으로 따라간다', async () => {
    const { w, advance } = await live()
    expect(w.find('.floor-title').text()).toContain('Sprint 2')
    await advance()
    expect(w.find('.floor-title').text()).toContain('Sprint 3')
    expect(w.find('.follow-chip').exists()).toBe(false)
    w.unmount()
  })

  test('직접 층을 고른 뒤에는 따라가지 않고 알림 칩만 띄우며, 누르면 그 층으로 이동한다', async () => {
    const { w, advance } = await live()
    await w.findAll('nav.building-rail a.rail-floor').find((a) => a.attributes('aria-label')!.includes('Sprint 1'))!.trigger('click')
    await flush()
    expect(w.find('.floor-title').text()).toContain('Sprint 1')
    await advance()
    expect(w.find('.floor-title').text()).toContain('Sprint 1') // 보던 층 그대로
    const chip = w.find('.scene-alerts .follow-chip')
    expect(chip.text()).toContain('현재 Sprint가 3F로 바뀜')
    await chip.find('button.go').trigger('click')
    await flush()
    expect(w.find('.floor-title').text()).toContain('Sprint 3')
    expect(w.find('.follow-chip').exists()).toBe(false)
    w.unmount()
  })

  test('알림 칩은 닫을 수 있다', async () => {
    const { w, advance } = await live()
    await w.findAll('nav.building-rail a.rail-floor').find((a) => a.attributes('aria-label')!.includes('Sprint 1'))!.trigger('click')
    await flush()
    await advance()
    await w.find('.follow-chip button.close').trigger('click')
    expect(w.find('.follow-chip').exists()).toBe(false)
    w.unmount()
  })
})

describe('장면과 같은 DOM 좌석 목록', () => {
  test('구역별로 작업을 보여주고 선택을 알린다', async () => {
    const tasks = findScenario('building')!.snapshot.tasks.filter((t) => t.sprint_id === 'sp-2')
    const w = mount(SceneRoster, { props: { tasks, selectedTaskId: 't-api' } })
    expect(w.text()).toContain('구현 구역')
    expect(w.find('[aria-pressed="true"]').text()).toContain('할 일 조회·상태 변경 API')
    await w.findAll('button.seat')[0].trigger('click')
    expect(w.emitted('select')).toEqual([['t-contract']])
  })
})
