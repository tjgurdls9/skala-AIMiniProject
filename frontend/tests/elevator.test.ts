// 엘리베이터 연출: 문 닫힘 → 층 이동 → 문 열림 → 화면 전환. 층 선택: 자동 따라가기는 직접 고른 적이 없을 때만.
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'
import { DOORS_MS, rideTime, useElevator } from '../src/composables/useElevator'
import { useFloorSelection } from '../src/composables/useFloorSelection'

const ORDER = ['f4', 'f3', 'f2', 'f1'] // 위층부터

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

function elevator(motion = true, start = 'f2') {
  const target = ref<string | null>(start)
  const on = ref(motion)
  const scope = effectScope()
  const api = scope.run(() => useElevator({ target, order: () => ORDER, motion: () => on.value }))!
  return { api, target, on, scope }
}

describe('엘리베이터 연출', () => {
  test('처음에는 연출 없이 그 층에 문이 열린 채 있다', () => {
    const { api } = elevator()
    expect(api.shownId.value).toBe('f2')
    expect(api.cabId.value).toBe('f2')
    expect(api.phase.value).toBe('idle')
    expect(api.doorsOpen.value).toBe(true)
    expect(api.direction.value).toBeNull()
  })

  test('층을 바꾸면 문 닫힘 → 이동(층·방향 표시) → 문 열림 → 그 층 화면 순서로 진행한다', async () => {
    const { api, target } = elevator()
    target.value = 'f4' // 두 층 위
    await nextTick()
    expect(api.phase.value).toBe('closing')
    expect(api.doorsOpen.value).toBe(false)
    expect(api.shownId.value).toBe('f2') // 아직 이전 층 화면
    expect(api.cabId.value).toBe('f2')

    vi.advanceTimersByTime(DOORS_MS)
    expect(api.phase.value).toBe('moving')
    expect(api.cabId.value).toBe('f4')
    expect(api.displayId.value).toBe('f4')
    expect(api.direction.value).toBe('up')
    expect(api.shownId.value).toBe('f2') // 이동 중에도 화면은 그대로

    vi.advanceTimersByTime(rideTime(2))
    expect(api.phase.value).toBe('opening')
    expect(api.shownId.value).toBe('f4') // 문이 열릴 때 화면이 그 층으로 바뀐다
    expect(api.doorsOpen.value).toBe(true)

    vi.advanceTimersByTime(DOORS_MS)
    expect(api.phase.value).toBe('idle')
    expect(api.direction.value).toBeNull()
  })

  test('아래층으로 가면 ▼, 이동 시간은 층 수에 비례하되 상한이 있다', async () => {
    const { api, target } = elevator(true, 'f4')
    target.value = 'f1'
    await nextTick()
    vi.advanceTimersByTime(DOORS_MS)
    expect(api.direction.value).toBe('down')
    expect(rideTime(3)).toBeGreaterThan(rideTime(1))
    expect(rideTime(50)).toBeLessThanOrEqual(1200)
  })

  test('이동 중에 다시 고르면 마지막으로 고른 층으로 이어서 간다', async () => {
    const { api, target } = elevator()
    target.value = 'f4'
    await nextTick()
    vi.advanceTimersByTime(DOORS_MS + 50)
    target.value = 'f1' // 이동 중 재선택
    await nextTick()
    vi.advanceTimersByTime(DOORS_MS * 4 + rideTime(3) * 3)
    expect(api.shownId.value).toBe('f1')
    expect(api.cabId.value).toBe('f1')
    expect(api.phase.value).toBe('idle')
    expect(api.doorsOpen.value).toBe(true)
  })

  test('이동 중 재선택은 순간이동하지 않고 칸이 다음 목적지로 이어서 움직인다', async () => {
    const { api, target } = elevator()
    target.value = 'f4'
    await nextTick()
    vi.advanceTimersByTime(DOORS_MS + 10) // 이동 시작(칸은 f4로)
    target.value = 'f1'
    await nextTick()
    vi.advanceTimersByTime(rideTime(2)) // 첫 구간 끝: 아직 문은 닫혀 있고 칸이 f1로 출발
    expect(api.phase.value).toBe('moving')
    expect(api.cabId.value).toBe('f1')
    expect(api.direction.value).toBe('down')
    expect(api.doorsOpen.value).toBe(false)
    expect(api.shownId.value).toBe('f2')
  })

  test('문이 열리는 중에 다른 층을 고르면 열린 뒤 다시 닫히고 그 층으로 간다', async () => {
    const { api, target } = elevator()
    target.value = 'f3'
    await nextTick()
    vi.advanceTimersByTime(DOORS_MS + rideTime(1) + 10)
    expect(api.phase.value).toBe('opening')
    target.value = 'f1'
    await nextTick()
    vi.advanceTimersByTime(DOORS_MS) // 열림 끝 → 새 목적지로 닫힘 시작
    expect(api.shownId.value).toBe('f3')
    expect(api.phase.value).toBe('closing')
    vi.advanceTimersByTime(DOORS_MS + rideTime(2) + DOORS_MS + 20)
    expect(api.shownId.value).toBe('f1')
    expect(api.phase.value).toBe('idle')
  })

  test('스냅샷이 오기 전(층 없음)에서 첫 층이 정해질 때는 연출 없이 그 층에 있다', async () => {
    const target = ref<string | null>(null)
    const api = effectScope().run(() => useElevator({ target, order: () => ORDER, motion: () => true }))!
    target.value = 'f2'
    await nextTick()
    expect(api.shownId.value).toBe('f2')
    expect(api.cabId.value).toBe('f2')
    expect(api.phase.value).toBe('idle')
    expect(api.doorsOpen.value).toBe(true)
  })

  test('같은 층을 다시 고르면 움직이지 않는다', async () => {
    const { api, target } = elevator()
    target.value = 'f2'
    await nextTick()
    expect(api.phase.value).toBe('idle')
  })

  test('모션이 꺼져 있으면(모션 감소 포함) 애니메이션 없이 바로 전환한다', async () => {
    const { api, target } = elevator(false)
    target.value = 'f4'
    await nextTick()
    expect(api.shownId.value).toBe('f4')
    expect(api.cabId.value).toBe('f4')
    expect(api.phase.value).toBe('idle')
    expect(api.doorsOpen.value).toBe(true)
    expect(api.direction.value).toBeNull()
  })

  test('이동 중 모션이 꺼지면 바로 도착한다', async () => {
    const { api, target, on } = elevator()
    target.value = 'f4'
    await nextTick()
    on.value = false
    await nextTick()
    expect(api.shownId.value).toBe('f4')
    expect(api.phase.value).toBe('idle')
  })

  test('해제하면 남은 타이머를 정리한다', async () => {
    const { api, target, scope } = elevator()
    target.value = 'f4'
    await nextTick()
    scope.stop()
    const phase = api.phase.value
    vi.advanceTimersByTime(5000)
    expect(api.phase.value).toBe(phase)
  })
})

describe('층 선택: 자동 따라가기', () => {
  function selection(first: string | null = 'f1', current: string | null = 'f1') {
    const currentId = ref<string | null>(current)
    const firstId = ref<string | null>(first)
    const scope = effectScope()
    const api = scope.run(() => useFloorSelection({ currentId, firstId }))!
    return { api, currentId, firstId }
  }

  test('처음에는 현재 Sprint 층을 고른다(알림 없음)', async () => {
    const { api } = selection('f1', 'f2')
    await nextTick()
    expect(api.selectedId.value).toBe('f2')
    expect(api.notice.value).toBeNull()
  })

  test('직접 고른 적이 없으면 현재 Sprint가 바뀔 때 따라간다', async () => {
    const { api, currentId } = selection('f1', 'f2')
    await nextTick()
    currentId.value = 'f3'
    await nextTick()
    expect(api.selectedId.value).toBe('f3')
    expect(api.notice.value).toBeNull()
  })

  test('직접 고른 뒤에는 따라가지 않고 알림만 남긴다', async () => {
    const { api, currentId } = selection('f1', 'f2')
    await nextTick()
    api.pick('f1')
    currentId.value = 'f3'
    await nextTick()
    expect(api.selectedId.value).toBe('f1')
    expect(api.notice.value).toBe('f3')
  })

  test('알림 층으로 가거나 알림을 닫으면 알림이 사라진다', async () => {
    const { api, currentId } = selection('f1', 'f2')
    await nextTick()
    api.pick('f1')
    currentId.value = 'f3'
    await nextTick()
    api.dismiss()
    expect(api.notice.value).toBeNull()
    currentId.value = 'f4'
    await nextTick()
    expect(api.notice.value).toBe('f4')
    api.pick('f4')
    expect(api.notice.value).toBeNull()
  })

  test('이미 보고 있는 층으로 현재 Sprint가 바뀌면 알림이 필요 없다', async () => {
    const { api, currentId } = selection('f1', 'f2')
    await nextTick()
    api.pick('f3')
    currentId.value = 'f3'
    await nextTick()
    expect(api.notice.value).toBeNull()
  })

  test('현재 Sprint를 아직 도출하지 못하면 첫 층을 고르고 나중에 도출되면 따라간다', async () => {
    const { api, currentId } = selection('f1', null)
    await nextTick()
    expect(api.selectedId.value).toBe('f1')
    currentId.value = 'f2'
    await nextTick()
    expect(api.selectedId.value).toBe('f2')
  })
})
