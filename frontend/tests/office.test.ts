import { describe, expect, test } from 'vitest'
import { buildEvents } from '../src/examples/base'
import { findScenario } from '../src/examples/scenarios'
import { runAlerts } from '../src/model/alerts'
import { packetFor } from '../src/office/draw'
import { computeLayout, fitGrid, hitSeat, zoneCenter, zoneRects } from '../src/office/layout'
import { resolveTheme } from '../src/composables/theme'

const snap = (id: string) => findScenario(id)!.snapshot
const inside = (s: { x: number; y: number; w: number; h: number }, z: { x: number; y: number; w: number; h: number }) =>
  s.x >= z.x - 0.01 && s.y >= z.y - 0.01 && s.x + s.w <= z.x + z.w + 0.01 && s.y + s.h <= z.y + z.h + 0.01

describe('사무실 배치', () => {
  test('넓은 화면은 회의실→구현→검증·보안→출시 한 줄, 좁은 화면은 두 줄', () => {
    expect(zoneRects(1000, 360).compact).toBe(false)
    expect(zoneRects(390, 340).compact).toBe(true)
    const wide = zoneRects(1000, 360).zones
    expect(wide.map((z) => z.id)).toEqual(['meeting', 'build', 'validate', 'security', 'release'])
    expect(wide.find((z) => z.id === 'validate')!.y).toBeLessThan(wide.find((z) => z.id === 'security')!.y)
  })

  test.each([[1000, 360], [700, 300], [390, 340]])('%ix%i: 좌석이 역할 구역 안에 겹치지 않게 놓인다', (w, h) => {
    const tasks = snap('building').tasks.filter((t) => t.sprint_id === 'sp-2')
    const layout = computeLayout(w, h, [...tasks, ...snap('review-split').tasks.filter((t) => t.sprint_id === 'sp-4')])
    for (const seat of layout.seats) {
      expect(inside(seat, layout.zones.find((z) => z.id === seat.zone)!)).toBe(true)
    }
    for (let i = 0; i < layout.seats.length; i++) {
      for (let j = i + 1; j < layout.seats.length; j++) {
        const a = layout.seats[i]
        const b = layout.seats[j]
        const overlap = a.x < b.x + b.w - 0.01 && b.x < a.x + a.w - 0.01 && a.y < b.y + b.h - 0.01 && b.y < a.y + a.h - 0.01
        expect(overlap).toBe(false)
      }
    }
  })

  test('대체된 작업은 장면에 놓지 않는다', () => {
    const [t] = snap('building').tasks
    expect(computeLayout(800, 300, [{ ...t, state: 'superseded' }]).seats).toHaveLength(0)
  })

  test('좌석이 많으면 배율을 줄여 맞춘다', () => {
    expect(fitGrid(1, 400, 300).scale).toBeGreaterThan(1.5)
    expect(fitGrid(40, 200, 100).scale).toBeLessThan(0.5)
  })

  test('클릭 좌표로 좌석을 찾는다', () => {
    const tasks = snap('building').tasks.filter((t) => t.sprint_id === 'sp-2')
    const layout = computeLayout(1000, 360, tasks)
    const seat = layout.seats[0]
    expect(hitSeat(layout, seat.x + 2, seat.y + 2)).toBe(seat.taskId)
    expect(hitSeat(layout, 1, 1)).toBeNull()
    expect(zoneCenter(layout, 'release').x).toBeGreaterThan(zoneCenter(layout, 'meeting').x)
  })
})

describe('사건 연출', () => {
  const tasks = snap('building').tasks.filter((t) => t.sprint_id === 'sp-2')
  const layout = computeLayout(1000, 360, tasks)
  const byId = new Map(tasks.map((t) => [t.id, t]))
  const ev = (type: Parameters<typeof buildEvents>[0][0][0], taskId?: string) =>
    buildEvents([[type, 's', taskId ? { task_id: taskId } : {}]])[0]

  test('근거 사건은 근거 패킷, 장면에 없는 작업·상태 사건은 연출하지 않는다', () => {
    expect(packetFor(ev('tool_finished', 't-api'), layout, byId, 0)?.kind).toBe('evidence')
    expect(packetFor(ev('review_submitted', 't-api'), layout, byId, 0)?.kind).toBe('report')
    expect(packetFor(ev('warning', 't-api'), layout, byId, 0)?.kind).toBe('alert')
    expect(packetFor(ev('tool_finished', 't-ui'), layout, byId, 0)).toBeNull()
    expect(packetFor(ev('run_state_changed'), layout, byId, 0)).toBeNull()
    expect(packetFor(ev('task_started', 't-api'), layout, byId, 0)).toBeNull()
  })

  test('작업 종료 색은 스냅샷 상태가 확인된 경우에만 성공/실패로 칠한다', () => {
    expect(packetFor(ev('task_finished', 't-data'), layout, byId, 0)?.kind).toBe('done')
    expect(packetFor(ev('task_finished', 't-api'), layout, byId, 0)?.kind).toBe('evidence')
    const failed = new Map([...byId, ['t-api', { ...byId.get('t-api')!, state: 'failed' as const }]])
    expect(packetFor(ev('task_finished', 't-api'), layout, failed, 0)?.kind).toBe('alert')
  })
})

describe('고정 알림', () => {
  test('승인 대기·보안 실패·작업 실패·한도 대기가 항상 포함된다', () => {
    expect(runAlerts(snap('plan-approval')).map((a) => a.key)).toEqual(['plan'])
    expect(runAlerts(snap('release-approval')).map((a) => a.key)).toEqual(['release'])
    expect(runAlerts(snap('preview')).map((a) => a.key)).toEqual(['preview'])
    const split = runAlerts(snap('review-split')).map((a) => a.key)
    expect(split).toEqual(['report-rp-security', 'task-t-security'])
    expect(runAlerts(snap('quota')).map((a) => a.key)).toContain('quota')
    expect(runAlerts(snap('failed')).map((a) => a.key)).toEqual(['failed', 'task-t-int'])
    expect(runAlerts(snap('building')).map((a) => a.key)).toEqual(['task-t-infra'])
    expect(runAlerts({ ...snap('building'), state: 'waiting_resource' }).map((a) => a.key)).toContain('resource')
    expect(runAlerts({ ...snap('building'), state: 'needs_input', reason: '문맥 초과' })[0].text).toContain('문맥 초과')
    expect(runAlerts(snap('succeeded'))).toEqual([])
  })
})

describe('표시 테마', () => {
  test('시스템 설정은 OS 선호를 따르고 명시 선택은 그대로', () => {
    expect(resolveTheme('system', true)).toBe('dark')
    expect(resolveTheme('system', false)).toBe('light')
    expect(resolveTheme('dark', false)).toBe('dark')
  })
})
