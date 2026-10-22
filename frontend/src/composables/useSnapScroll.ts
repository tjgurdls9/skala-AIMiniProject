import { onBeforeUnmount, onMounted, ref } from 'vue'

/**
 * 전체 화면(full) ↔ 상세(detail) 두 상태 사이를 "저항 있는" 스크롤로 오간다.
 * 짧은 휠·드래그는 화면을 바꾸지 않고 살짝 늘어나는 표시만 준 뒤 되돌아간다.
 * 누적 입력이 임계값을 넘을 때만 전환하고, 전환 직후의 관성 입력은 잠시 무시한다.
 */
export type SnapMode = 'full' | 'detail'

export const WHEEL_THRESHOLD = 240
export const TOUCH_THRESHOLD = 120
/** 입력이 멈추면 쌓인 값을 버리고 되돌아가는 시간 */
export const IDLE_RESET_MS = 220
/** 전환 뒤 관성 휠을 흘려보내는 시간 */
export const COOLDOWN_MS = 450
/** 키보드·스크롤바로 중간에 멈췄을 때 가까운 상태로 맞추기까지 기다리는 시간 */
export const SETTLE_MS = 140
const TWEEN_MS = 420
/** 저항 표시: 임계값까지 진행도 최대 이만큼만 미리 움직인다 */
const RUBBER_MAX = 0.08
const LINE_PX = 16

export function rubber(pull: number, threshold: number): number {
  const t = Math.min(1, Math.abs(pull) / threshold)
  return Math.sign(pull) * RUBBER_MAX * (1 - (1 - t) ** 2)
}

export interface SnapOptions {
  /** 상세 상태의 스크롤 위치(px) */
  distance: () => number
  reducedMotion?: () => boolean
}

export function useSnapScroll(options: SnapOptions) {
  const progress = ref(0)
  const mode = ref<SnapMode>('full')

  let pull = 0
  let resist = 0
  let idleTimer: ReturnType<typeof setTimeout> | null = null
  let settleTimer: ReturnType<typeof setTimeout> | null = null
  let lockedUntil = 0
  let tweenRaf = 0
  let animating = false
  let touchY: number | null = null

  const now = () => performance.now()
  const reduce = () => options.reducedMotion?.() ?? window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false

  function render(): void {
    const d = Math.max(1, options.distance())
    const base = Math.min(1, Math.max(0, window.scrollY / d))
    progress.value = Math.min(1, Math.max(0, base + resist))
  }

  /** 전환 구간 안에 있는가(상세 상태에서 더 아래로 내려간 경우는 일반 스크롤) */
  function inZone(direction: number): boolean {
    const d = options.distance()
    if (window.scrollY < d - 1) return true
    return direction < 0 && window.scrollY <= d + 1
  }

  function resetPull(): void {
    pull = 0
    resist = 0
    render()
  }

  function commit(target: SnapMode): void {
    if (idleTimer) clearTimeout(idleTimer)
    idleTimer = null
    pull = 0
    resist = 0
    mode.value = target
    const to = target === 'full' ? 0 : options.distance()
    lockedUntil = now() + COOLDOWN_MS
    cancelAnimationFrame(tweenRaf)
    if (reduce()) {
      window.scrollTo(0, to)
      render()
      return
    }
    const from = window.scrollY
    const start = now()
    animating = true
    const step = () => {
      const t = Math.min(1, (now() - start) / TWEEN_MS)
      const ease = 1 - (1 - t) ** 3
      window.scrollTo(0, from + (to - from) * ease)
      render()
      if (t < 1) tweenRaf = requestAnimationFrame(step)
      else {
        animating = false
        lockedUntil = now() + COOLDOWN_MS
      }
    }
    tweenRaf = requestAnimationFrame(step)
  }

  /** 누적값을 더하고, 임계값을 넘으면 전환, 아니면 늘어남만 보여 주고 멈추면 되돌린다 */
  function accumulate(delta: number, threshold: number): void {
    const direction = mode.value === 'full' ? 1 : -1
    // 현재 상태에서 나가는 방향만 쌓는다(반대 방향은 되돌림)
    pull = Math.max(0, pull * direction + delta * direction) * direction
    resist = rubber(pull, threshold)
    render()
    if (Math.abs(pull) >= threshold) {
      commit(mode.value === 'full' ? 'detail' : 'full')
      return
    }
    if (idleTimer) clearTimeout(idleTimer)
    idleTimer = setTimeout(resetPull, IDLE_RESET_MS)
  }

  /** 승인·프리뷰 같은 모달 대화상자가 열려 있으면 입력은 창의 것이다. 쌓인 입력은 버리고 막지 않는다 */
  function yieldToDialog(): boolean {
    if (!document.querySelector('dialog[open]')) return false
    touchY = null
    if (pull !== 0 || resist !== 0) resetPull()
    return true
  }

  function onWheel(e: WheelEvent): void {
    if (yieldToDialog()) return
    const delta = e.deltaMode === 1 ? e.deltaY * LINE_PX : e.deltaY
    if (!inZone(delta)) return
    e.preventDefault()
    if (animating || now() < lockedUntil) return
    accumulate(delta, WHEEL_THRESHOLD)
  }

  function onTouchStart(e: TouchEvent): void {
    if (yieldToDialog()) return
    touchY = e.touches[0]?.clientY ?? null
  }

  function onTouchMove(e: TouchEvent): void {
    if (yieldToDialog() || touchY === null) return
    const y = e.touches[0]?.clientY ?? touchY
    const delta = touchY - y
    if (!inZone(delta)) return
    e.preventDefault()
    if (animating || now() < lockedUntil) return
    const direction = mode.value === 'full' ? 1 : -1
    pull = Math.max(0, delta * direction) * direction
    resist = rubber(pull, TOUCH_THRESHOLD)
    render()
  }

  function onTouchEnd(): void {
    if (touchY === null) return
    touchY = null
    if (Math.abs(pull) >= TOUCH_THRESHOLD) commit(mode.value === 'full' ? 'detail' : 'full')
    else resetPull()
  }

  /** 키보드·스크롤바로 구간 중간에서 멈추면 가까운 상태로 맞춘다 */
  function onScroll(): void {
    render()
    if (animating) return
    const d = options.distance()
    if (window.scrollY >= d) mode.value = 'detail'
    else if (window.scrollY <= 0) mode.value = 'full'
    if (settleTimer) clearTimeout(settleTimer)
    if (window.scrollY > 0 && window.scrollY < d) {
      settleTimer = setTimeout(() => {
        if (animating || touchY !== null) return
        commit(window.scrollY >= d / 2 ? 'detail' : 'full')
      }, SETTLE_MS)
    }
  }

  onMounted(() => {
    window.addEventListener('wheel', onWheel, { passive: false })
    window.addEventListener('touchstart', onTouchStart, { passive: true })
    window.addEventListener('touchmove', onTouchMove, { passive: false })
    window.addEventListener('touchend', onTouchEnd)
    window.addEventListener('touchcancel', onTouchEnd)
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', render)
    mode.value = window.scrollY >= options.distance() ? 'detail' : 'full'
    render()
  })

  onBeforeUnmount(() => {
    window.removeEventListener('wheel', onWheel)
    window.removeEventListener('touchstart', onTouchStart)
    window.removeEventListener('touchmove', onTouchMove)
    window.removeEventListener('touchend', onTouchEnd)
    window.removeEventListener('touchcancel', onTouchEnd)
    window.removeEventListener('scroll', onScroll)
    window.removeEventListener('resize', render)
    if (idleTimer) clearTimeout(idleTimer)
    if (settleTimer) clearTimeout(settleTimer)
    cancelAnimationFrame(tweenRaf)
  })

  return { progress, mode, commit, render }
}
