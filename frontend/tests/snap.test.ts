// 사용자 피드백: 짧은 드래그로 전체 화면 ↔ 상세가 바뀌지 않게, 누적 입력이 쌓여야 전환
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import {
  COOLDOWN_MS, IDLE_RESET_MS, rubber, SETTLE_MS, TOUCH_THRESHOLD, useSnapScroll, WHEEL_THRESHOLD,
} from '../src/composables/useSnapScroll'

const DISTANCE = 500
let scrollY = 0

function setScroll(y: number): void {
  scrollY = y
  Object.defineProperty(window, 'scrollY', { value: y, configurable: true })
}

function host(reduced = true) {
  let api!: ReturnType<typeof useSnapScroll>
  const Host = defineComponent({
    setup() {
      api = useSnapScroll({ distance: () => DISTANCE, reducedMotion: () => reduced })
      return () => h('div')
    },
  })
  const wrapper = mount(Host)
  return { wrapper, api: () => api }
}

function wheel(deltaY: number, deltaMode = 0): WheelEvent {
  const e = new WheelEvent('wheel', { deltaY, deltaMode, cancelable: true })
  window.dispatchEvent(e)
  return e
}

function touch(type: string, clientY?: number): void {
  const e = new Event(type, { cancelable: true }) as Event & { touches: Array<{ clientY: number }> }
  Object.defineProperty(e, 'touches', { value: clientY === undefined ? [] : [{ clientY }] })
  window.dispatchEvent(e)
}

beforeEach(() => {
  vi.useFakeTimers()
  setScroll(0)
  vi.spyOn(window, 'scrollTo').mockImplementation(((x: number | ScrollToOptions, y?: number) => {
    setScroll(typeof x === 'number' ? (y ?? 0) : (x.top ?? 0))
  }) as typeof window.scrollTo)
})
afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
  setScroll(0)
})

describe('저항 표시', () => {
  test('임계값까지 진행도를 최대 0.08만 미리 움직인다', () => {
    expect(rubber(0, 240)).toBe(0)
    expect(rubber(240, 240)).toBeCloseTo(0.08)
    expect(rubber(9999, 240)).toBeCloseTo(0.08)
    expect(rubber(-120, 240)).toBeLessThan(0)
  })
})

describe('휠', () => {
  test('짧은 휠은 화면을 바꾸지 않고 살짝 늘어났다가 멈추면 되돌아간다', () => {
    const { wrapper, api } = host()
    const e = wheel(100)
    expect(e.defaultPrevented).toBe(true)
    expect(api().mode.value).toBe('full')
    expect(api().progress.value).toBeGreaterThan(0)
    expect(api().progress.value).toBeLessThanOrEqual(0.08)
    expect(window.scrollTo).not.toHaveBeenCalled()
    vi.advanceTimersByTime(IDLE_RESET_MS)
    expect(api().progress.value).toBe(0)
    wrapper.unmount()
  })

  test('누적이 임계값을 넘으면 상세로 전환하고, 직후 관성 입력은 무시한다', () => {
    const { wrapper, api } = host()
    wheel(WHEEL_THRESHOLD / 2)
    wheel(WHEEL_THRESHOLD / 2)
    expect(api().mode.value).toBe('detail')
    expect(scrollY).toBe(DISTANCE)
    expect(api().progress.value).toBe(1)
    // 관성: 위로 큰 입력이 와도 쿨다운 동안은 돌아가지 않는다
    wheel(-WHEEL_THRESHOLD * 2)
    expect(api().mode.value).toBe('detail')
    vi.advanceTimersByTime(COOLDOWN_MS + 1)
    wrapper.unmount()
  })

  test('멈췄다가 다시 시작하면 처음부터 다시 쌓는다', () => {
    const { wrapper, api } = host()
    wheel(WHEEL_THRESHOLD - 10)
    vi.advanceTimersByTime(IDLE_RESET_MS)
    wheel(20)
    expect(api().mode.value).toBe('full')
    wrapper.unmount()
  })

  test('반대 방향 입력은 쌓인 값을 줄인다', () => {
    const { wrapper, api } = host()
    wheel(200)
    wheel(-150)
    wheel(100)
    expect(api().mode.value).toBe('full')
    wrapper.unmount()
  })

  test('상세에서 위로도 같은 저항을 거쳐 전체 화면으로 돌아간다', () => {
    setScroll(DISTANCE)
    const { wrapper, api } = host()
    expect(api().mode.value).toBe('detail')
    wheel(-100)
    expect(api().mode.value).toBe('detail')
    wheel(-WHEEL_THRESHOLD)
    expect(api().mode.value).toBe('full')
    expect(scrollY).toBe(0)
    wrapper.unmount()
  })

  test('상세 아래쪽을 읽는 중의 휠은 막지 않는다(일반 스크롤)', () => {
    setScroll(DISTANCE + 300)
    const { wrapper } = host()
    expect(wheel(-50).defaultPrevented).toBe(false)
    expect(wheel(50).defaultPrevented).toBe(false)
    wrapper.unmount()
  })

  test('줄 단위 휠도 픽셀로 환산한다', () => {
    const { wrapper, api } = host()
    wheel(16, 1) // 16줄 = 256px
    expect(api().mode.value).toBe('detail')
    wrapper.unmount()
  })
})

describe('터치 드래그', () => {
  test('짧은 드래그는 놓으면 되돌아가고, 충분히 끌어야 전환한다', () => {
    const { wrapper, api } = host()
    touch('touchstart', 600)
    touch('touchmove', 560)
    expect(api().progress.value).toBeGreaterThan(0)
    touch('touchend')
    expect(api().mode.value).toBe('full')
    expect(api().progress.value).toBe(0)

    touch('touchstart', 600)
    touch('touchmove', 600 - TOUCH_THRESHOLD - 10)
    touch('touchend')
    expect(api().mode.value).toBe('detail')
    wrapper.unmount()
  })
})

describe('키보드·스크롤바로 중간에 멈춘 경우', () => {
  test('가까운 상태로 맞춘다', () => {
    const { wrapper, api } = host()
    setScroll(DISTANCE * 0.3)
    window.dispatchEvent(new Event('scroll'))
    vi.advanceTimersByTime(SETTLE_MS)
    expect(api().mode.value).toBe('full')
    expect(scrollY).toBe(0)

    setScroll(DISTANCE * 0.7)
    window.dispatchEvent(new Event('scroll'))
    vi.advanceTimersByTime(SETTLE_MS)
    expect(api().mode.value).toBe('detail')
    expect(scrollY).toBe(DISTANCE)
    wrapper.unmount()
  })
})

describe('모션이 켜져 있으면', () => {
  test('부드럽게 이동한 뒤 목표에 도착한다', () => {
    const { wrapper, api } = host(false)
    api().commit('detail')
    vi.advanceTimersByTime(1000)
    expect(scrollY).toBe(DISTANCE)
    expect(api().progress.value).toBe(1)
    wrapper.unmount()
  })
})
