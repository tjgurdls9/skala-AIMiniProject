import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeAll, beforeEach, describe, expect, test, vi } from 'vitest'
import type { RunEvent, RunState, Snapshot } from '../src/api/types'
import ModelWorkNotice from '../src/components/ModelWorkNotice.vue'
import RunWorkspace from '../src/components/RunWorkspace.vue'
import { exampleSource } from '../src/examples/exampleSource'
import { fullCycleSource } from '../src/examples/fullCycle'
import { findScenario } from '../src/examples/scenarios'
import { formatIdle, idleSeconds, modelWork } from '../src/model/modelWork'

// 로컬 모델이 오래 걸려 사건이 없을 때 화면이 멈춘 것처럼 보이지 않게 한다. 표시는 서버 상태와 사건에서만 도출한다.

const building = findScenario('building')!
const snap = (state: RunState, extra: Partial<Snapshot> = {}): Snapshot => ({ ...building.snapshot, state, ...extra })
const eventAt = (occurred_at: string): RunEvent => ({ ...building.events.at(-1)!, occurred_at })

const NOW = Date.parse('2026-10-22T09:30:00+09:00')

beforeAll(() => {
  const proto = HTMLDialogElement.prototype as HTMLDialogElement & { showModal(): void }
  if (!proto.showModal) proto.showModal = function (this: HTMLDialogElement) { this.setAttribute('open', '') }
  if (!('ResizeObserver' in globalThis)) {
    ;(globalThis as Record<string, unknown>).ResizeObserver = class { observe() {} disconnect() {} }
  }
})
beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(NOW)
})
afterEach(() => {
  vi.useRealTimers()
  document.body.innerHTML = ''
})

describe('표시 조건', () => {
  test.each(['planning', 'building', 'reviewing'] as RunState[])('%s에서는 모델 작업 대기 표시를 보인다', (state) => {
    expect(modelWork(snap(state))).not.toBeNull()
  })

  test.each([
    'awaiting_plan_approval', 'preview_ready', 'awaiting_release_approval', 'deploying', 'succeeded',
    'paused', 'waiting_resource', 'waiting_quota', 'needs_input', 'failed', 'cancelled',
  ] as RunState[])('%s에서는 보이지 않고 기존 결정·알림 UI를 쓴다', (state) => {
    expect(modelWork(snap(state))).toBeNull()
  })

  test('단계 이름은 서버 상태에서, 진행 중 작업은 서버 작업 상태에서 나온다', () => {
    const work = modelWork(snap('building'))!
    expect(work.stage).toBe('구현 중')
    expect(work.running).toEqual(['할 일 조회·상태 변경 API'])
    expect(modelWork(snap('planning'))!.stage).toBe('기획 중')
    expect(modelWork(snap('reviewing'))!.stage).toBe('검증·보안 검토 중')
  })
})

describe('경과 시간', () => {
  test('마지막 사건 시각이 올바르면 그것을 기준으로 센다', () => {
    expect(idleSeconds('2026-10-22T09:29:30+09:00', NOW - 1000, NOW)).toBe(30)
  })

  test('시계가 조금 어긋나 미래로 찍혀도 0초로 본다', () => {
    expect(idleSeconds('2026-10-22T09:30:03+09:00', NOW - 1000, NOW)).toBe(0)
  })

  test.each([
    ['하루보다 오래된 시각(합성 예시 등)', '2026-10-20T09:00:00+09:00'],
    ['먼 미래', '2026-10-23T09:00:00+09:00'],
    ['해석할 수 없는 값', 'not-a-date'],
    ['시각이 없음', undefined],
  ])('%s이면 화면이 사건을 받은 시각으로 센다', (_name, at) => {
    expect(idleSeconds(at, NOW - 12_000, NOW)).toBe(12)
  })

  test.each([
    [0, '0초'], [59, '59초'], [60, '1분'], [75, '1분 15초'], [3600, '1시간'], [3725, '1시간 2분'],
  ])('%i초를 %s로 적는다', (sec, text) => {
    expect(formatIdle(sec)).toBe(text)
  })
})

describe('표시 모양', () => {
  const mountNotice = (props: Partial<InstanceType<typeof ModelWorkNotice>['$props']> = {}) =>
    mount(ModelWorkNotice, { attachTo: document.body, props: { snapshot: snap('planning'), lastEvent: null, receivedAt: NOW, animated: true, ...props } })

  test('단계와 응답 대기, 마지막 사건, 경과 시간을 알리고 진행률·남은 시간은 쓰지 않는다', async () => {
    const w = mountNotice({ snapshot: snap('building'), lastEvent: eventAt('2026-10-22T09:29:50+09:00') })
    const text = w.text()
    expect(text).toContain('구현 중')
    expect(text).toContain('응답 대기')
    expect(text).toContain(building.events.at(-1)!.summary)
    expect(text).toContain('마지막 진행 10초 전')
    expect(text).toContain('할 일 조회·상태 변경 API')
    expect(text).not.toMatch(/%|남은|예상|완료까지/)
    w.unmount()
  })

  test('경과 시간이 1초마다 늘어난다', async () => {
    const w = mountNotice({ lastEvent: null, receivedAt: NOW })
    expect(w.text()).toContain('마지막 진행 0초 전')
    await vi.advanceTimersByTimeAsync(5000)
    expect(w.text()).toContain('마지막 진행 5초 전')
    await vi.advanceTimersByTimeAsync(60_000)
    expect(w.text()).toContain('마지막 진행 1분 5초 전')
    w.unmount()
  })

  test('새 사건을 받으면 경과 시간이 다시 0부터 센다', async () => {
    const w = mountNotice({ receivedAt: NOW })
    await vi.advanceTimersByTimeAsync(20_000)
    expect(w.text()).toContain('20초 전')
    await w.setProps({ receivedAt: Date.now() })
    expect(w.text()).toContain('마지막 진행 0초 전')
    w.unmount()
  })

  test('승인 대기·입력 필요·중지·실패에서는 아무것도 그리지 않는다', async () => {
    for (const state of ['awaiting_plan_approval', 'needs_input', 'paused', 'failed'] as RunState[]) {
      const w = mountNotice({ snapshot: snap(state) })
      expect(w.find('.work-pill').exists()).toBe(false)
      expect(w.text()).toBe('')
      w.unmount()
    }
  })

  test('모션이 꺼져 있으면 애니메이션 표시가 없고 정적으로 보인다', () => {
    const on = mountNotice({ animated: true })
    expect(on.find('.spin').classes()).toContain('animated')
    on.unmount()
    const off = mountNotice({ animated: false })
    expect(off.find('.spin').classes()).not.toContain('animated')
    expect(off.text()).toContain('응답 대기')
    off.unmount()
  })

  test('보이는 표시는 스크린리더에서 숨기고 상태 변화만 polite로 한 번 알린다', async () => {
    const w = mountNotice({ snapshot: snap('planning') })
    expect(w.get('.work-pill').attributes('aria-hidden')).toBe('true')
    const live = w.get('[role="status"]')
    expect(live.attributes('aria-live')).toBe('polite')
    expect(live.text()).toBe('기획 중 · 로컬 모델 응답 대기')
    await vi.advanceTimersByTimeAsync(30_000)
    expect(w.get('[role="status"]').text()).toBe('기획 중 · 로컬 모델 응답 대기')

    await w.setProps({ snapshot: snap('awaiting_plan_approval') })
    expect(w.get('[role="status"]').text()).toBe('')
    w.unmount()
  })
})

describe('작업 화면', () => {
  const live = (state: RunState, mode: Snapshot['mode'] = 'live') => {
    const scenario = { ...building, snapshot: snap(state, { mode }) }
    return { ...exampleSource(scenario), kind: 'live' as const }
  }
  const tick = async (ms = 0) => {
    await vi.advanceTimersByTimeAsync(ms)
    await flushPromises()
  }

  test('실서버 연결에서 구현 중이면 보인다', async () => {
    const w = mount(RunWorkspace, { attachTo: document.body, props: { source: live('building') } })
    await tick(50)
    expect(w.find('.work-pill').exists()).toBe(true)
    expect(w.text()).toContain('로컬 모델 응답 대기')
    w.unmount()
  })

  test.each(['awaiting_plan_approval', 'needs_input', 'failed'] as RunState[])('실서버 연결에서도 %s이면 보이지 않는다', async (state) => {
    const w = mount(RunWorkspace, { attachTo: document.body, props: { source: live(state) } })
    await tick(50)
    expect(w.find('.work-pill').exists()).toBe(false)
    w.unmount()
  })

  test('기록 재생은 동결된 기록이라 보이지 않는다', async () => {
    const w = mount(RunWorkspace, { attachTo: document.body, props: { source: live('building', 'replay') } })
    await tick(50)
    expect(w.find('.work-pill').exists()).toBe(false)
    w.unmount()
  })

  test('정지된 합성 예시 화면에는 보이지 않는다', async () => {
    const w = mount(RunWorkspace, { attachTo: document.body, props: { source: exampleSource(building) } })
    await tick(50)
    expect(w.find('.work-pill').exists()).toBe(false)
    w.unmount()
  })

  test('합성 시연의 자동 진행 구간에는 보이고, 승인 대기에서는 사라지며, 합성 배지는 그대로다', async () => {
    const source = fullCycleSource({ startDelayMs: 100, eventGapMs: 10, stagePauseMs: 50 })
    const w = mount(RunWorkspace, { attachTo: document.body, props: { source } })
    await tick(0)
    let seenWork = false
    for (let i = 0; i < 40 && !source.demo.info().waiting; i++) {
      await tick(20)
      if (w.find('.work-pill').exists()) {
        seenWork = true
        expect(w.text()).toContain('합성 시연 · 실제 모델 실행 아님')
      }
    }
    expect(seenWork).toBe(true)
    await tick(10_000)
    expect(source.demo.info().waiting).toBe('plan')
    expect(w.find('.work-pill').exists()).toBe(false)
    expect(w.text()).toContain('합성 시연 · 실제 모델 실행 아님')
    w.unmount()
  })
})
