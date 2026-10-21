import { computed, onScopeDispose, ref, watch, type Ref } from 'vue'

/**
 * 엘리베이터 연출(사용자 디자인 지시): 문 닫힘 → 층 이동(표시창에 층·방향) → 문 열림 → 화면이 그 층으로 전환.
 * 모션이 꺼져 있으면(모션 감소 포함) 연출 없이 바로 도착한다. 이동 중에 다시 고르면 마지막 선택으로 이어서 간다.
 */
export type ElevatorPhase = 'idle' | 'closing' | 'moving' | 'opening'

/** 문이 닫히거나 열리는 시간(CSS 문 전환 시간과 맞춘다) */
export const DOORS_MS = 700
const RIDE_BASE_MS = 240
const RIDE_PER_FLOOR_MS = 180
const RIDE_MAX_MS = 1200

export const rideTime = (floors: number): number => Math.min(RIDE_MAX_MS, RIDE_BASE_MS + Math.abs(floors) * RIDE_PER_FLOOR_MS)

interface Options {
  /** 가려는 층(사용자가 고르거나 자동으로 따라간 층) */
  target: Ref<string | null>
  /** 층 순서: 위층부터. 앞쪽 인덱스가 위층이다 */
  order: () => readonly string[]
  motion: () => boolean
}

export function useElevator(options: Options) {
  const shownId = ref<string | null>(options.target.value)
  const cabId = ref<string | null>(options.target.value)
  const displayId = ref<string | null>(options.target.value)
  const phase = ref<ElevatorPhase>('idle')
  const direction = ref<'up' | 'down' | null>(null)
  const rideMs = ref(0)
  let timer: ReturnType<typeof setTimeout> | null = null

  const clear = (): void => {
    if (timer) clearTimeout(timer)
    timer = null
  }
  const arrive = (id: string | null): void => {
    clear()
    shownId.value = id
    cabId.value = id
    displayId.value = id
    phase.value = 'idle'
    direction.value = null
  }
  const after = (ms: number, fn: () => void): void => {
    clear()
    timer = setTimeout(fn, ms)
  }

  /** 칸이 있는 층에서 지금 목표 층까지 한 구간 이동. 도착 때 목표가 또 바뀌었으면 문을 닫은 채 다음 구간으로 이어 간다 */
  function ride(): void {
    const goal = options.target.value
    const list = options.order()
    const from = list.indexOf(cabId.value ?? '')
    const to = list.indexOf(goal ?? '')
    if (goal === null || from < 0 || to < 0 || from === to) {
      open()
      return
    }
    cabId.value = goal
    displayId.value = goal
    direction.value = to < from ? 'up' : 'down'
    rideMs.value = rideTime(to - from)
    phase.value = 'moving'
    after(rideMs.value, () => (options.target.value === cabId.value ? open() : ride()))
  }

  /** 문 열림과 함께 화면이 칸이 있는 층으로 바뀐다. 열리는 동안 목표가 또 바뀌었으면 닫고 다시 간다 */
  function open(): void {
    phase.value = 'opening'
    direction.value = null
    shownId.value = cabId.value
    after(DOORS_MS, () => {
      if (options.target.value !== shownId.value && options.motion()) begin()
      else arrive(options.target.value ?? shownId.value)
    })
  }

  function begin(): void {
    phase.value = 'closing'
    after(DOORS_MS, ride)
  }

  watch(options.target, (next) => {
    if (next === shownId.value && phase.value === 'idle') return
    // 처음 층이 정해지는 순간(이전 층 없음)이나 모션이 꺼진 경우는 연출 없이 바로 도착한다
    if (!options.motion() || shownId.value === null) {
      arrive(next)
      return
    }
    // 진행 중이면 그 연출을 끝낸 뒤 이어서 간다(각 단계가 최신 목표를 읽는다)
    if (phase.value === 'idle') begin()
  })
  watch(
    () => options.motion(),
    (on) => {
      if (!on && phase.value !== 'idle') arrive(options.target.value)
    },
  )
  onScopeDispose(clear)

  return {
    /** 화면에 보이는 층 */
    shownId,
    /** 칸이 있는 층 */
    cabId,
    /** 표시창의 층 */
    displayId,
    phase,
    direction,
    rideMs,
    doorsOpen: computed(() => phase.value === 'idle' || phase.value === 'opening'),
  }
}
