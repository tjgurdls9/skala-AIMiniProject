import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeAll, describe, expect, test } from 'vitest'
import type { RunEvent } from '../src/api/types'
import OfficeScene from '../src/components/OfficeScene.vue'
import { buildEvents } from '../src/examples/base'
import { findScenario } from '../src/examples/scenarios'
import { runAlerts } from '../src/model/alerts'
import { bubbleFor, flashFor, ISO_ZONES, placeSeats, project } from '../src/office/iso'
import { resolveTheme } from '../src/composables/theme'

const snap = (id: string) => findScenario(id)!.snapshot

beforeAll(() => {
  if (!('ResizeObserver' in globalThis)) {
    ;(globalThis as Record<string, unknown>).ResizeObserver = class { observe() {} disconnect() {} }
  }
})
afterEach(() => {
  document.body.innerHTML = ''
})

describe('등각 사무실 배치', () => {
  test('평면 좌표를 등각 투영한다(평면 중심 → 층 상자 중심, 길이 축은 오른쪽 아래로)', () => {
    expect(project(200, 450)).toEqual({ x: 480, y: 310 })
    const near = project(200, 100)
    const far = project(200, 800)
    expect(far.x).toBeGreaterThan(near.x)
    expect(far.y).toBeGreaterThan(near.y)
  })

  test('구역은 업무 흐름 순서이고 검증실과 보안실은 나뉘어 있다', () => {
    expect(ISO_ZONES.map((z) => z.id)).toEqual(['meeting', 'build', 'validate', 'security', 'release'])
    const v = ISO_ZONES.find((z) => z.id === 'validate')!
    const s = ISO_ZONES.find((z) => z.id === 'security')!
    expect(v.x >= s.x + s.w || s.x >= v.x + v.w).toBe(true)
  })

  test('작업은 역할 구역의 자리에 겹치지 않게 앉고, 대체된 작업은 놓지 않으며 넘친 수를 남긴다', () => {
    const tasks = [...snap('building').tasks.filter((t) => t.sprint_id === 'sp-2'), ...snap('review-split').tasks.filter((t) => t.sprint_id === 'sp-4')]
    const { seats } = placeSeats(tasks)
    expect(seats.length).toBe(6)
    for (const seat of seats) {
      const z = ISO_ZONES.find((zone) => zone.id === seat.zone)!
      expect(seat.px).toBeGreaterThanOrEqual(z.x)
      expect(seat.px).toBeLessThanOrEqual(z.x + z.w)
      expect(seat.py).toBeGreaterThanOrEqual(z.y)
      expect(seat.py).toBeLessThanOrEqual(z.y + z.h)
    }
    expect(new Set(seats.map((s) => `${s.px},${s.py}`)).size).toBe(seats.length)
    const one = snap('building').tasks.find((t) => t.role === 'security') ?? { ...tasks[0], role: 'security' as const }
    const crowd = Array.from({ length: 6 }, (_, i) => ({ ...one, id: `sec-${i}`, role: 'security' as const, state: 'pending' as const }))
    const placed = placeSeats([...crowd, { ...crowd[0], id: 'gone', state: 'superseded' as const }])
    expect(placed.seats.every((s) => s.taskId !== 'gone')).toBe(true)
    expect(placed.overflow.security).toBe(6 - placed.seats.length)
  })

  test('말풍선은 스냅샷 상태에서만 정하고, 대기 작업에는 띄우지 않는다', () => {
    const t = snap('building').tasks[0]
    expect(bubbleFor({ ...t, state: 'running' })?.text).toBe('작업 중')
    expect(bubbleFor({ ...t, state: 'failed' })?.tone).toBe('danger')
    expect(bubbleFor({ ...t, state: 'blocked' })?.text).toBe('막힘')
    expect(bubbleFor({ ...t, state: 'succeeded' })?.text).toBe('완료')
    expect(bubbleFor({ ...t, state: 'pending' })).toBeNull()
    expect(bubbleFor({ ...t, state: 'ready' })).toBeNull()
  })

  test('최근 공개 사건은 잠깐 보이는 말풍선이 되고, 상태 사건·작업 없는 사건은 무시한다', () => {
    const ev = (type: RunEvent['event_type'], taskId?: string) => ({ ...buildEvents([[type, 's', taskId ? { task_id: taskId } : {}]])[0] })
    expect(flashFor(ev('task_finished', 't-api'))).toBe('방금 끝남')
    expect(flashFor(ev('review_submitted', 't-api'))).toBe('보고서 제출')
    expect(flashFor(ev('tool_finished', 't-api'))).toBe('근거 저장')
    expect(flashFor(ev('warning', 't-api'))).toBe('확인 필요')
    expect(flashFor(ev('task_started', 't-api'))).toBeNull()
    expect(flashFor(ev('task_finished'))).toBeNull()
  })
})

describe('등각 사무실 장면', () => {
  const tasks = snap('building').tasks.filter((t) => t.sprint_id === 'sp-2')
  function scene(extra: Record<string, unknown> = {}) {
    let push: ((e: RunEvent) => void) | null = null
    const w = mount(OfficeScene, {
      attachTo: document.body,
      props: { tasks, selectedTaskId: 't-api', motion: false, subscribe: (fn: (e: RunEvent) => void) => { push = fn; return () => {} }, ...extra },
    })
    return { w, push: (e: RunEvent) => push!(e) }
  }

  test('앉은 작업마다 이름이 붙은 버튼이 있고, 누르면 선택한다', async () => {
    const { w } = scene()
    const people = w.findAll('button.person')
    expect(people.length).toBe(tasks.length)
    const api = people.find((b) => b.attributes('aria-label')!.includes('문의 조회·상태 변경 API'))!
    expect(api.attributes('aria-pressed')).toBe('true')
    expect(api.attributes('aria-label')).toContain('구현')
    await people.find((b) => b !== api)!.trigger('click')
    expect(w.emitted('select')).toHaveLength(1)
    w.unmount()
  })

  test('사람의 결정을 기다리면 점선 실루엣과 대기 말풍선을 보인다', () => {
    const { w } = scene({ waiting: { text: '답 기다림 · 기획 승인', zone: 'meeting' } })
    expect(w.find('.ghost').text()).toContain('답 기다림 · 기획 승인')
    w.unmount()
    const none = scene()
    expect(none.w.find('.ghost').exists()).toBe(false)
    none.w.unmount()
  })

  test('작업 종료 사건이 오면 그 자리에 "방금 끝남"이 잠깐 뜬다', async () => {
    const { w, push } = scene()
    push({ ...buildEvents([['task_finished', '끝', { task_id: 't-api' }]])[0] })
    await flushPromises()
    const api = w.findAll('button.person').find((b) => b.attributes('aria-label')!.includes('문의 조회·상태 변경 API'))!
    expect(api.text()).toContain('방금 끝남')
    w.unmount()
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
