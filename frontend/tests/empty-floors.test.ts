import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeAll, describe, expect, test, vi } from 'vitest'
import BuildingRail from '../src/components/BuildingRail.vue'
import OfficeScene from '../src/components/OfficeScene.vue'
import RunWorkspace from '../src/components/RunWorkspace.vue'
import { exampleSource } from '../src/examples/exampleSource'
import { findScenario } from '../src/examples/scenarios'

// 기획 검증에서 멈춘 실제 기록은 phase·sprint·작업이 하나도 없다. 그래도 사무실이 비어 보이지 않아야 한다.
// 서버가 주지 않은 층·작업은 지어내지 않고, 자리표시임을 화면에 분명히 적는다.

const base = findScenario('plan-approval')!
const REASON = 'verification 단계에서 같은 오류가 반복돼 사람의 입력이 필요합니다: c3: 작업 공간을 벗어나거나 저장소 내부를 가리키는 경로입니다.'

function emptyRun(extra: Record<string, unknown> = {}) {
  const snapshot = {
    ...base.snapshot, state: 'needs_input', reason: REASON, spec_version_id: null,
    phases: [], sprints: [], tasks: [], approvals: [], reports: [], artifacts: [], last_event_seq: 0, ...extra,
  }
  return { ...exampleSource({ ...base, snapshot: snapshot as never, events: [], tail: [] }), kind: 'live' as const }
}

beforeAll(() => {
  const proto = HTMLDialogElement.prototype as HTMLDialogElement & { showModal(): void }
  if (!proto.showModal) proto.showModal = function (this: HTMLDialogElement) { this.setAttribute('open', '') }
  if (!('ResizeObserver' in globalThis)) {
    ;(globalThis as Record<string, unknown>).ResizeObserver = class { observe() {} disconnect() {} }
  }
})
afterEach(() => {
  document.body.innerHTML = ''
})

describe('층이 하나도 없는 실행', () => {
  test('사무실 장면을 비우지 않고 1F 기획 자리표시 층을 그린다', async () => {
    const w = mount(RunWorkspace, { attachTo: document.body, props: { source: emptyRun() } })
    await flushPromises()
    expect(w.findComponent(OfficeScene).exists()).toBe(true)
    const title = w.get('.floor-title').text()
    expect(title).toContain('1F')
    expect(title).toContain('자리표시')
    expect(title).toContain('아직 기획이 확정되지 않았습니다')
    expect(title).toContain('층(작업)이 만들어지지 않았습니다')
    w.unmount()
  })

  test('기획 회의실에 자리표시 말풍선을 보인다', async () => {
    const w = mount(RunWorkspace, { attachTo: document.body, props: { source: emptyRun({ state: 'planning', reason: undefined }) } })
    await flushPromises()
    expect(w.findComponent(OfficeScene).props('waiting')).toEqual({ text: '자리표시 · 기획 미확정', zone: 'meeting' })
    w.unmount()
  })

  test('입력 필요처럼 서버가 알린 대기 표시는 살리고 자리표시임을 앞에 붙인다', async () => {
    const w = mount(RunWorkspace, { attachTo: document.body, props: { source: emptyRun() } })
    await flushPromises()
    const waiting = w.findComponent(OfficeScene).props('waiting')
    expect(waiting).toMatchObject({ zone: 'meeting' })
    expect(waiting?.text).toBe('자리표시 · 답 기다림 · 입력 필요')
    w.unmount()
  })

  test('서버가 주지 않은 작업은 지어내지 않는다', async () => {
    const w = mount(RunWorkspace, { attachTo: document.body, props: { source: emptyRun() } })
    await flushPromises()
    expect(w.findComponent(OfficeScene).props('tasks')).toEqual([])
    w.unmount()
  })

  test('엘리베이터 레일에 자리표시 층 하나가 있어 쪼그라들지 않는다', async () => {
    const w = mount(RunWorkspace, { attachTo: document.body, props: { source: emptyRun() } })
    await flushPromises()
    const floors = w.findComponent(BuildingRail).props('floors')
    expect(floors).toHaveLength(1)
    expect(floors[0]).toMatchObject({ num: '1F' })
    expect(w.findAll('.rail-floor')).toHaveLength(1)
    w.unmount()
  })

  test('서버가 알린 입력 필요 알림과 이유는 그대로 보인다', async () => {
    const w = mount(RunWorkspace, { attachTo: document.body, props: { source: emptyRun() } })
    await flushPromises()
    expect(w.text()).toContain('입력 필요')
    expect(w.text()).toContain('작업 공간을 벗어나거나 저장소 내부를 가리키는 경로입니다')
    w.unmount()
  })

  test('승인 대기처럼 서버가 알린 대기 표시가 있으면 자리표시 말풍선보다 우선한다', async () => {
    const approval = base.snapshot.approvals.filter((a) => a.state === 'pending')
    const w = mount(RunWorkspace, {
      attachTo: document.body,
      props: { source: emptyRun({ state: 'awaiting_plan_approval', reason: undefined, approvals: approval }) },
    })
    await flushPromises()
    expect(w.findComponent(OfficeScene).props('waiting')).toMatchObject({ zone: 'meeting', text: '자리표시 · 답 기다림 · 기획 승인' })
    w.unmount()
  })

  test('층이 있는 실행에는 자리표시를 쓰지 않는다', async () => {
    const w = mount(RunWorkspace, { attachTo: document.body, props: { source: exampleSource(findScenario('building')!) } })
    await flushPromises()
    expect(w.get('.floor-title').text()).not.toContain('자리표시')
    expect(w.text()).not.toContain('기획 미확정')
    w.unmount()
  })
})

vi.useRealTimers()
