// DEV-P02 화면 연결: L2 재동기화 폭주 방지, L3 긴 이력, 재개 가능 상태, 입력 필요 재기획, 검색 근거 없음
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeAll, describe, expect, test, vi } from 'vitest'
import { LiveApi, liveSource } from '../src/api/live'
import type { RunSource, StreamHandlers } from '../src/api/source'
import type { RunState, Snapshot } from '../src/api/types'
import RunHeader from '../src/components/RunHeader.vue'
import RunWorkspace from '../src/components/RunWorkspace.vue'
import { gapDelay, useRun } from '../src/composables/useRun'
import { buildEvents } from '../src/examples/base'
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
  vi.useRealTimers()
  document.body.innerHTML = ''
  sessionStorage.clear()
})

const flush = async () => {
  await flushPromises()
  await new Promise((r) => setTimeout(r, 120))
  await flushPromises()
}
const base = findScenario('building')!.snapshot

function fake(initial: Snapshot) {
  const streams: Array<{ after: number; h: StreamHandlers }> = []
  const source: RunSource = {
    kind: 'live',
    runId: initial.run_id,
    getSnapshot: vi.fn(async () => initial),
    getRecording: vi.fn(),
    getAcceptance: vi.fn(async () => ({ spec_version_id: initial.spec_version_id, items: [] })),
    openEvents: vi.fn((after: number, h: StreamHandlers) => {
      streams.push({ after, h })
      return () => {}
    }),
    sendCommand: vi.fn(),
    getArtifact: vi.fn(),
    getEnvironment: vi.fn(),
  }
  return { source, streams }
}

describe('L2 누락 재동기화는 반복될수록 간격을 늘린다', () => {
  test('첫 누락은 즉시, 이후 지수 증가하되 최대 30초에서 멈춘다(횟수 상한 없음)', () => {
    expect([1, 2, 3, 4].map(gapDelay)).toEqual([0, 500, 1000, 2000])
    expect(gapDelay(50)).toBe(30_000)
  })

  test('연속 누락에는 바로 다시 열지 않고, 정상 사건이 오면 간격을 초기화한다', async () => {
    vi.useFakeTimers()
    const { source, streams } = fake({ ...base, state_version: 0, last_event_seq: 0 })
    const run = useRun(source)
    await run.start()
    const gapEvent = (seq: number) => buildEvents([['warning', 'x', {}]], seq, 0)[0]
    streams.at(-1)!.h.onEvent(gapEvent(5))
    expect(streams).toHaveLength(2) // 첫 누락 즉시
    streams.at(-1)!.h.onEvent(gapEvent(5))
    expect(streams).toHaveLength(2) // 두 번째는 대기
    expect(run.notice.value).toContain('반복 2회')
    await vi.advanceTimersByTimeAsync(500)
    expect(streams).toHaveLength(3)
    streams.at(-1)!.h.onEvent(gapEvent(1)) // 정상 사건
    streams.at(-1)!.h.onEvent(gapEvent(9))
    expect(streams).toHaveLength(4) // 간격 초기화 → 즉시
    run.dispose()
  })

  test('수동 다시 연결은 대기 중인 백오프를 취소한다', async () => {
    vi.useFakeTimers()
    const { source, streams } = fake({ ...base, state_version: 0, last_event_seq: 0 })
    const run = useRun(source)
    await run.start()
    const gap = buildEvents([['warning', 'x', {}]], 7, 0)[0]
    streams.at(-1)!.h.onEvent(gap)
    streams.at(-1)!.h.onEvent(gap)
    await run.reconnect()
    const count = streams.length
    await vi.advanceTimersByTimeAsync(60_000)
    expect(streams).toHaveLength(count)
    run.dispose()
  })

  test('형식이 맞지 않는 SSE 데이터는 조용히 버리지 않고 알린다', async () => {
    let es: { listeners: Record<string, (m: { data: string }) => void> } | null = null
    const api = new LiveApi(vi.fn() as unknown as typeof fetch, () => {
      const fakeEs = { listeners: {} as Record<string, (m: { data: string }) => void>, addEventListener(t: string, fn: (m: { data: string }) => void) { this.listeners[t] = fn }, close() {}, readyState: 1, onopen: null, onerror: null }
      es = fakeEs
      return fakeEs as unknown as EventSource
    })
    const src = { ...liveSource(api, base.run_id), getSnapshot: async () => base, getAcceptance: async () => ({ spec_version_id: null, items: [] }) }
    const run = useRun(src)
    await run.start()
    es!.listeners.lifecycle({ data: '{"broken"' })
    expect(run.notice.value).toContain('형식이 맞지 않는 사건')
    run.dispose()
  })
})

describe('L3 긴 이력', () => {
  test('사건 1만 건을 받아도 화면 목록은 묶어서 한 번에 게시한다', async () => {
    vi.useFakeTimers()
    const { source, streams } = fake({ ...base, state_version: 0, last_event_seq: 0 })
    const run = useRun(source)
    await run.start()
    const events = buildEvents(Array.from({ length: 10_000 }, () => ['tool_finished', 'e', {}] as never), 1, 0)
    const before = run.events.value
    const started = performance.now()
    events.forEach((e) => streams[0].h.onEvent(e))
    const elapsed = performance.now() - started
    expect(run.events.value).toBe(before) // 아직 게시 전(묶음 대기)
    await vi.advanceTimersByTimeAsync(100)
    expect(run.events.value).toHaveLength(10_000)
    expect(elapsed).toBeLessThan(1000)
    run.dispose()
  })
})

describe('재개·중지 버튼은 서버가 받는 상태를 따른다', () => {
  const header = (state: RunState) =>
    mount(RunHeader, {
      props: { kind: 'live', snapshot: { ...base, state }, connection: 'open', pending: null, isReplay: false, motion: true },
    }).findAll('button').map((b) => b.text())

  test.each([
    ['building', false, true, true],
    ['paused', true, false, true],
    ['waiting_resource', true, true, true],
    ['needs_input', true, true, true],
    ['failed', true, false, true],
    ['succeeded', false, false, false],
    ['cancelled', false, false, false],
  ] as const)('%s → 재개 %s · 일시 중지 %s · 취소 %s', (state, resume, pause, cancel) => {
    const buttons = header(state)
    expect(buttons.some((t) => t.includes('재개'))).toBe(resume)
    expect(buttons.some((t) => t.includes('일시 중지'))).toBe(pause)
    expect(buttons.some((t) => t.includes('실행 취소'))).toBe(cancel)
  })
})

describe('입력 필요·실패에서 수정 요청으로 재기획', () => {
  test('알림의 수정 요청이 이유를 보여주고 기획 변경 범위로 request_changes를 보낸다', async () => {
    const scenario = findScenario('failed')!
    const sent: unknown[] = []
    const source = { ...exampleSource(scenario), kind: 'live' as const, sendCommand: vi.fn(async (c: { command_id: string; run_id: string }) => { sent.push(c); return { command_id: c.command_id, run_id: c.run_id, status: 'accepted' as const, accepted_at: 'x' } }) }
    const w = mount(RunWorkspace, { attachTo: document.body, props: { source } })
    await flush()
    await w.find('.alerts').findAll('button').find((b) => b.text() === '수정 요청')!.trigger('click')
    await flush()
    const dialog = document.querySelector('dialog[open]')!
    expect(dialog.textContent).toContain('통합 확인 실패: 응답 형식 불일치')
    expect((dialog.querySelector('input[value="spec"]') as HTMLInputElement).checked).toBe(true)
    const textarea = dialog.querySelector('textarea')!
    textarea.value = '응답 필드 이름을 계약에 맞춰 다시 기획'
    textarea.dispatchEvent(new Event('input'))
    await flush()
    dialog.querySelector('form')!.dispatchEvent(new Event('submit'))
    await flush()
    expect(sent[0]).toMatchObject({ action: 'request_changes', payload: { scope: 'spec', feedback: '응답 필드 이름을 계약에 맞춰 다시 기획' } })
    w.unmount()
  })
})

describe('검색 근거', () => {
  test('공개된 검색·문맥 근거가 없으면 없음으로 보여준다', async () => {
    const w = mount(RunWorkspace, { attachTo: document.body, props: { source: exampleSource(findScenario('failed')!) } })
    await flush()
    await w.findAll('nav.tree button').find((b) => b.text().includes('Sprint 1'))!.trigger('click')
    await flush()
    await w.findAll('button').find((b) => b.text().includes('요청 분석·기획안 작성'))!.trigger('click')
    await flush()
    const text = w.find('aside.evidence').text()
    expect(text).toContain('공개된 검색·문맥 근거가 없습니다')
    expect(text).toContain('검색 사건 1건은 기록에 있음')
    w.unmount()
  })
})
