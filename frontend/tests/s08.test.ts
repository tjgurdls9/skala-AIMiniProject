// DEV-S08 사용자 디자인 지시 구현: 빈 화면 입력 → 전환 → 건물형 사무실(층 = Sprint)
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

describe('건물형 사무실: 실행 = 건물, Sprint = 층', () => {
  async function open(id: string) {
    const w = mount(RunWorkspace, { attachTo: document.body, props: { source: exampleSource(findScenario(id)!) } })
    await flush()
    return w
  }

  test('Sprint마다 층 하나를 위층부터 쌓고, 왼쪽 층 목록도 같은 순서다', async () => {
    const w = await open('building')
    const sprints = findScenario('building')!.snapshot.sprints
    const floors = w.findAll('section.floor')
    expect(floors).toHaveLength(sprints.length)
    expect(floors[0].find('.floor-num').text()).toBe(`${sprints.length}F`)
    expect(floors[0].text()).toContain(sprints[sprints.length - 1].title)
    expect(floors.at(-1)!.find('.floor-num').text()).toBe('1F')
    const links = w.findAll('nav.building-rail a.rail-floor')
    expect(links.map((a) => a.find('.floor-num').text())).toEqual(floors.map((f) => f.find('.floor-num').text()))
    // 현재 Sprint 층이 선택돼 있다
    expect(w.find('section.floor.selected').text()).toContain('Sprint 2')
    expect(w.find('nav.building-rail a[aria-current="true"]').text()).toContain('Sprint 2')
    w.unmount()
  })

  test('층 목록을 누르면 그 Sprint 층을 고르고, 층의 사람을 누르면 근거 패널이 그 작업을 연다', async () => {
    const w = await open('building')
    await w.findAll('nav.building-rail a.rail-floor').find((a) => a.text().includes('Sprint 1'))!.trigger('click')
    await flush()
    expect(w.find('section.floor.selected').text()).toContain('Sprint 1')
    const person = w.findAll('button.person').find((b) => b.attributes('aria-label')!.includes('문의 조회·상태 변경 API'))!
    await person.trigger('click')
    await flush()
    expect(w.find('aside.evidence').text()).toContain('문의 조회·상태 변경 API')
    expect(w.find('section.floor.selected').text()).toContain('Sprint 2')
    w.unmount()
  })

  test('층 이동은 엘리베이터: 표시창이 고른 층과 방향을 보이고, 칸이 그 층 자리로 가며 그 층 문만 열린다', async () => {
    const w = await open('building')
    const floors = w.findAll('section.floor')
    const indexOf = (label: string) => floors.findIndex((f) => f.text().includes(label))
    expect(w.find('.elevator-display').text()).toContain('2F')
    expect(w.find('.cab').attributes('style')).toContain(`--stop: ${indexOf('Sprint 2')}`)
    expect(w.findAll('.elevator.open')).toHaveLength(1)
    expect(w.find('section.floor.selected .elevator.open').exists()).toBe(true)
    await w.findAll('nav.building-rail a.rail-floor').find((a) => a.text().includes('Sprint 4'))!.trigger('click')
    await flushPromises()
    expect(w.find('.elevator-display').text()).toContain('4F')
    expect(w.find('.elevator-display').text()).toContain('▲')
    expect(w.find('.cab').attributes('style')).toContain(`--stop: ${indexOf('Sprint 4')}`)
    expect(w.find('section.floor.selected .elevator.open').exists()).toBe(true)
    expect(w.findAll('.elevator.open')).toHaveLength(1)
    w.unmount()
  })

  test('결정·문제 배너는 고정 순서로 보이고, 누르면 해당 동작을 연다', async () => {
    const w = await open('plan-approval')
    const items = w.findAll('.decision-banner button')
    expect(items).toHaveLength(1)
    await items[0].trigger('click')
    await flush()
    expect(document.querySelector('dialog[open]')?.textContent).toContain('기획 승인')
    w.unmount()
  })

  test('사람의 결정 대기는 현재 Sprint 층에만 점선 실루엣으로 보인다', async () => {
    const w = await open('plan-approval')
    expect(w.findAll('.ghost')).toHaveLength(1)
    expect(w.find('section.floor.current .ghost').text()).toContain('답 기다림 · 기획 승인')
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
