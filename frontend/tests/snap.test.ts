// 사용자 피드백: 짧은 드래그로 전체 화면 ↔ 상세가 바뀌지 않게, 누적 입력이 쌓여야 전환
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import {
  BURST_GAP_MS, COOLDOWN_MS, IDLE_RESET_MS, rubber, SETTLE_MS, TICK_MEMORY_MS, TICKS_TO_COMMIT, TOUCH_THRESHOLD, useSnapScroll, WHEEL_THRESHOLD,
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
  document.body.innerHTML = ''
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

describe('대화상자가 열려 있으면 (승인·프리뷰 창)', () => {
  function openDialog(): HTMLDialogElement {
    const d = document.createElement('dialog')
    d.setAttribute('open', '')
    document.body.append(d)
    return d
  }

  test('휠을 막지 않아 창 안이 스크롤되고, 뒤의 사무실은 상세로 내려가지 않는다', () => {
    const { wrapper, api } = host()
    openDialog()
    expect(wheel(100).defaultPrevented).toBe(false)
    expect(wheel(WHEEL_THRESHOLD * 2).defaultPrevented).toBe(false)
    expect(api().mode.value).toBe('full')
    expect(api().progress.value).toBe(0)
    expect(window.scrollTo).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  test('터치 드래그도 막지 않고 전환하지 않는다', () => {
    const { wrapper, api } = host()
    openDialog()
    touch('touchstart', 600)
    const move = new Event('touchmove', { cancelable: true }) as Event & { touches: Array<{ clientY: number }> }
    Object.defineProperty(move, 'touches', { value: [{ clientY: 600 - TOUCH_THRESHOLD * 2 }] })
    window.dispatchEvent(move)
    expect(move.defaultPrevented).toBe(false)
    touch('touchend')
    expect(api().mode.value).toBe('full')
    expect(api().progress.value).toBe(0)
    wrapper.unmount()
  })

  test('창이 열리기 전에 쌓인 입력은 버리고, 닫히면 다시 처음부터 쌓는다', () => {
    const { wrapper, api } = host()
    wheel(150)
    const dialog = openDialog()
    wheel(200)
    expect(api().progress.value).toBe(0)
    dialog.remove()
    expect(wheel(150).defaultPrevented).toBe(true)
    expect(api().mode.value).toBe('full')
    wheel(150)
    expect(api().mode.value).toBe('detail')
    wrapper.unmount()
  })

  test('닫힌 대화상자(open 아님)는 막지 않는다', () => {
    const { wrapper, api } = host()
    document.body.append(document.createElement('dialog'))
    expect(wheel(100).defaultPrevented).toBe(true)
    expect(api().progress.value).toBeGreaterThan(0)
    wrapper.unmount()
  })
})

describe('마우스 휠 한 칸씩 굴리기 (칸 사이가 길어도 칸 수로 센다)', () => {
  const SLOW_MS = 300

  function notches(count: number, deltaY: number, gap = SLOW_MS): void {
    for (let i = 0; i < count; i++) {
      wheel(deltaY)
      vi.advanceTimersByTime(gap)
    }
  }

  test('0.3초 간격으로 세 칸을 굴리면 상세로 전환한다', () => {
    const { wrapper, api } = host()
    expect(TICKS_TO_COMMIT).toBe(3)
    expect(SLOW_MS).toBeGreaterThan(IDLE_RESET_MS)
    notches(2, 100)
    expect(api().mode.value).toBe('full')
    wheel(100)
    expect(api().mode.value).toBe('detail')
    expect(scrollY).toBe(DISTANCE)
    wrapper.unmount()
  })

  test('한 칸이나 두 칸만 굴리고 멈추면 전환하지 않고 되돌아간다', () => {
    const { wrapper, api } = host()
    notches(1, 100)
    vi.advanceTimersByTime(TICK_MEMORY_MS + 1)
    expect(api().mode.value).toBe('full')
    expect(api().progress.value).toBe(0)

    notches(2, 100)
    vi.advanceTimersByTime(TICK_MEMORY_MS + 1)
    expect(api().mode.value).toBe('full')
    wrapper.unmount()
  })

  test('칸 사이가 너무 길면 처음부터 다시 센다', () => {
    const { wrapper, api } = host()
    notches(3, 100, TICK_MEMORY_MS + 100)
    expect(api().mode.value).toBe('full')
    wrapper.unmount()
  })

  test('칸당 델타가 아주 작은 마우스도 세 칸이면 전환한다', () => {
    const { wrapper, api } = host()
    notches(2, 4)
    wheel(4)
    expect(api().mode.value).toBe('detail')
    wrapper.unmount()
  })

  test('줄 단위 한 칸씩도 센다', () => {
    const { wrapper, api } = host()
    for (let i = 0; i < 2; i++) {
      wheel(1, 1)
      vi.advanceTimersByTime(SLOW_MS)
    }
    wheel(1, 1)
    expect(api().mode.value).toBe('detail')
    wrapper.unmount()
  })

  test('반대로 굴리면 센 칸을 버린다', () => {
    const { wrapper, api } = host()
    notches(2, 100)
    notches(1, -100)
    notches(2, 100)
    expect(api().mode.value).toBe('full')
    wheel(100)
    expect(api().mode.value).toBe('detail')
    wrapper.unmount()
  })

  test('상세에서 위로도 세 칸이면 전체 화면으로 돌아간다', () => {
    setScroll(DISTANCE)
    const { wrapper, api } = host()
    notches(2, -100)
    expect(api().mode.value).toBe('detail')
    wheel(-100)
    expect(api().mode.value).toBe('full')
    expect(scrollY).toBe(0)
    wrapper.unmount()
  })

  test('트랙패드처럼 이어지는 작은 델타는 한 번의 굴림이라 기존대로 누적 크기로만 전환한다', () => {
    const { wrapper, api } = host()
    expect(BURST_GAP_MS).toBeGreaterThan(16)
    for (let i = 0; i < 20; i++) {
      wheel(5)
      vi.advanceTimersByTime(10)
    }
    expect(api().mode.value).toBe('full')

    vi.advanceTimersByTime(TICK_MEMORY_MS + 1)
    for (let i = 0; i < 40; i++) {
      wheel(8)
      vi.advanceTimersByTime(10)
    }
    expect(api().mode.value).toBe('detail')
    wrapper.unmount()
  })
})
