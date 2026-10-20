import { describe, expect, test } from 'vitest'
import { buildEvents } from '../src/examples/base'
import { findScenario } from '../src/examples/scenarios'
import { runAlerts } from '../src/model/alerts'
import { packetFor } from '../src/office/draw'
import { chooseMap, computeLayout, fitMap, hitSeat, seatSlots, TILE, zoneCenter } from '../src/office/layout'
import { resolveTheme } from '../src/composables/theme'

const snap = (id: string) => findScenario(id)!.snapshot
const inside = (s: { x: number; y: number; w: number; h: number }, z: { x: number; y: number; w: number; h: number }) =>
  s.x >= z.x - 0.01 && s.y >= z.y - 0.01 && s.x + s.w <= z.x + z.w + 0.01 && s.y + s.h <= z.y + z.h + 0.01

describe('사무실 배치(타일 지도)', () => {
  test('가로 화면은 회의실→구현→검증·보안→출시 한 줄, 세로·좁은 화면은 두 줄 지도', () => {
    const wide = chooseMap(1400, 800)
    expect(wide.compact).toBe(false)
    expect(wide.map.rooms.map((r) => r.id)).toEqual(['meeting', 'build', 'validate', 'security', 'release'])
    const v = wide.map.rooms.find((r) => r.id === 'validate')!
    const sec = wide.map.rooms.find((r) => r.id === 'security')!
    expect(v.y + v.h).toBeLessThan(sec.y) // 검증실과 보안실 사이에 벽
    expect(chooseMap(390, 760).compact).toBe(true)
  })

  test('지도를 화면에 맞추고 1배 이상은 0.25 단위로 내린다', () => {
    const { map } = chooseMap(1400, 800)
    const fit = fitMap(map, 1400, 800)
    expect(fit.scale % 0.25).toBe(0)
    expect(map.w * TILE * fit.scale).toBeLessThanOrEqual(1400)
    expect(map.h * TILE * fit.scale).toBeLessThanOrEqual(800)
    expect(fitMap(map, 300, 200).scale).toBeLessThan(1)
  })

  test('좌석은 표지판 아래, 큰 방의 가구 자리 위에 놓인다', () => {
    const { map } = chooseMap(1400, 800)
    for (const room of map.rooms) {
      for (const slot of seatSlots(room)) {
        expect(slot.ty).toBeGreaterThan(room.y + 1)
        expect(slot.ty + 3).toBeLessThanOrEqual(room.y + room.h)
        expect(slot.tx + 3).toBeLessThanOrEqual(room.x + room.w)
      }
    }
  })

  test.each([[1400, 800], [1000, 600], [390, 760]])('%ix%i: 좌석이 역할 구역 안에 겹치지 않게 놓인다', (w, h) => {
    const tasks = snap('building').tasks.filter((t) => t.sprint_id === 'sp-2')
    const layout = computeLayout(w, h, [...tasks, ...snap('review-split').tasks.filter((t) => t.sprint_id === 'sp-4')])
    expect(layout.seats.length).toBe(6)
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

  test('방에 다 못 놓은 작업 수를 남기고, 대체된 작업은 놓지 않는다', () => {
    const [t] = snap('building').tasks
    const many = Array.from({ length: 30 }, (_, i) => ({ ...t, id: `t${i}`, role: 'validator' as const }))
    const layout = computeLayout(1400, 800, many)
    expect(layout.overflow.validate).toBeGreaterThan(0)
    expect(layout.seats.length + (layout.overflow.validate ?? 0)).toBe(30)
    expect(computeLayout(800, 300, [{ ...t, state: 'superseded' }]).seats).toHaveLength(0)
  })

  test('클릭 좌표로 좌석을 찾고, 표지판 위치는 지도 좌표다', () => {
    const tasks = snap('building').tasks.filter((t) => t.sprint_id === 'sp-2')
    const layout = computeLayout(1400, 800, tasks)
    const seat = layout.seats[0]
    expect(hitSeat(layout, seat.x + 2, seat.y + 2)).toBe(seat.taskId)
    expect(hitSeat(layout, 1, 1)).toBeNull()
    expect(zoneCenter(layout, 'release').x).toBeGreaterThan(zoneCenter(layout, 'meeting').x)
  })
})

describe('사건 연출', () => {
  const tasks = snap('building').tasks.filter((t) => t.sprint_id === 'sp-2')
  const layout = computeLayout(1400, 800, tasks)
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
