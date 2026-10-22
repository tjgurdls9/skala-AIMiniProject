import Ajv2020 from 'ajv/dist/2020'
import addFormats from 'ajv-formats'
import { flushPromises, mount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, beforeAll, beforeEach, describe, expect, test, vi } from 'vitest'
import App from '../src/App.vue'
import type { Command, RunEvent } from '../src/api/types'
import DemoControl from '../src/components/DemoControl.vue'
import RunWorkspace from '../src/components/RunWorkspace.vue'
import StartScreen from '../src/components/StartScreen.vue'
import { fakeDigest } from '../src/examples/base'
import { FULL_CYCLE_BADGE, FULL_CYCLE_ID, buildFullCycle, fullCycleSource } from '../src/examples/fullCycle'

// 합성 시연: 실제 사무실 UI 위에서 한 실행이 처음부터 끝까지 진행된다. 서버로는 아무것도 보내지 않는다.

const dir = resolve(__dirname, '../../docs/planning')
const ajv = new Ajv2020({ strict: false, allErrors: true })
addFormats(ajv)
ajv.addSchema(JSON.parse(readFileSync(resolve(dir, 'protocol.v1.schema.json'), 'utf8')), 'protocol.v1.schema.json')
const check = (ref: string, value: unknown): string[] => {
  const validate = ajv.getSchema(ref)
  if (!validate) throw new Error(`schema ${ref} not found`)
  return validate(value) ? [] : (validate.errors ?? []).map((e) => `${e.instancePath} ${e.message}`)
}

const FAST = { startDelayMs: 100, eventGapMs: 10, stagePauseMs: 50 }
const LONG = 600_000
const PLAN_DIGEST = fakeDigest('d1')
const ACCEPTANCE_DIGEST = fakeDigest('d4')

function open(source: ReturnType<typeof fullCycleSource>, afterSeq = 0) {
  const events: RunEvent[] = []
  const close = source.openEvents(afterSeq, { onEvent: (e) => events.push(e), onResync() {}, onOpen() {}, onDown() {} })
  return { events, close }
}

function decide(approvalId: string, digest: string, decision: 'approve' | 'reject' = 'approve', commandId = `c-${approvalId}`): Command {
  return {
    kind: 'command', protocol_version: 1, command_id: commandId, run_id: 'example-run', expected_state_version: 0,
    action: 'decide', payload: { approval_id: approvalId, target_digest: digest, decision },
  } as Command
}

beforeAll(() => {
  const proto = HTMLDialogElement.prototype as HTMLDialogElement & { showModal(): void }
  if (!proto.showModal) proto.showModal = function (this: HTMLDialogElement) { this.setAttribute('open', '') }
  if (!('ResizeObserver' in globalThis)) {
    ;(globalThis as Record<string, unknown>).ResizeObserver = class { observe() {} disconnect() {} }
  }
})
beforeEach(() => {
  vi.useFakeTimers()
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
  window.history.replaceState(null, '', '/')
})

describe('단계 구성', () => {
  const { stages, events } = buildFullCycle()

  test('요청부터 배포 승인 대상까지 순서대로 진행한다', () => {
    const states = stages.map((s) => s.snapshot.state)
    expect(states[0]).toBe('planning')
    expect(states.at(-1)).toBe('awaiting_release_approval')
    const order = ['planning', 'awaiting_plan_approval', 'building', 'reviewing', 'preview_ready', 'awaiting_release_approval']
    const firstSeen = order.map((s) => states.indexOf(s as (typeof states)[number]))
    expect(firstSeen.every((i) => i >= 0)).toBe(true)
    expect([...firstSeen].sort((a, b) => a - b)).toEqual(firstSeen)
  })

  test('사람 결정 지점은 기획 승인과 사람 확인 둘이고 각각 대기 승인이 있다', () => {
    const gates = stages.filter((s) => s.gate)
    expect(gates.map((s) => s.gate)).toEqual(['plan', 'acceptance'])
    expect(gates[0]!.snapshot.state).toBe('awaiting_plan_approval')
    expect(gates[0]!.snapshot.approvals.filter((a) => a.state === 'pending').map((a) => a.id)).toEqual(['ap-plan-1'])
    expect(gates[1]!.snapshot.state).toBe('preview_ready')
    expect(gates[1]!.snapshot.approvals.filter((a) => a.state === 'pending').map((a) => a.id)).toEqual(['ap-acceptance-1'])
  })

  test('마지막 단계는 승인된 사람 확인에 묶인 배포 승인 대상이다', () => {
    const last = stages.at(-1)!
    const release = last.snapshot.approvals.find((a) => a.target.gate === 'release')
    expect(release?.state).toBe('pending')
    const acceptance = last.snapshot.approvals.find((a) => a.target.gate === 'acceptance')
    expect(acceptance?.state).toBe('approved')
    expect(release?.target).toMatchObject({ acceptance_approval_id: acceptance?.id })
    expect(last.release?.state).toBe('prepared')
  })

  test('모든 층(Sprint)의 작업이 순서대로 시작된다', () => {
    const sprints = events.flatMap((e) => (e.sprint_id ? [e.sprint_id] : []))
    const firstIndex = ['sp-1', 'sp-2', 'sp-3', 'sp-4'].map((s) => sprints.indexOf(s))
    expect(firstIndex.every((i) => i >= 0)).toBe(true)
    expect([...firstIndex].sort((a, b) => a - b)).toEqual(firstIndex)
  })

  test('스냅샷·사건이 공유 계약에 맞고 seq가 연속이다', () => {
    events.forEach((e, i) => {
      expect(check('protocol.v1.schema.json#/$defs/Event', e)).toEqual([])
      expect(e.seq).toBe(i + 1)
    })
    stages.forEach((s) => {
      expect(check('protocol.v1.schema.json#/$defs/Snapshot', s.snapshot)).toEqual([])
      expect(s.snapshot.last_event_seq).toBe(s.end)
      expect(s.snapshot.state_version).toBe(events[s.end - 1]!.state_version)
    })
  })

  test('결과를 말하는 사건은 합성임을 밝히고 소재는 범용 할 일 앱이다', () => {
    const results = events.filter((e) => ['tool_finished', 'review_submitted', 'preview_ready'].includes(e.event_type))
    expect(results.length).toBeGreaterThan(0)
    results.forEach((e) => expect(e.summary).toContain('합성'))
    const text = JSON.stringify({ stages, events })
    for (const word of ['카공', '카페', '카카오', '문의', 'inquir', 'cafemap']) expect(text).not.toContain(word)
  })
})

describe('시연 소스 진행', () => {
  test('자동으로 진행하다 기획 승인에서 멈추고 승인 뒤에만 이어진다', async () => {
    const source = fullCycleSource(FAST)
    const { events } = open(source)

    await vi.advanceTimersByTimeAsync(LONG)
    expect((await source.getSnapshot()).state).toBe('awaiting_plan_approval')
    const stopped = events.length
    await vi.advanceTimersByTimeAsync(LONG)
    expect(events.length).toBe(stopped)
    expect(source.demo?.info().waiting).toBe('plan')

    await source.sendCommand(decide('ap-plan-1', PLAN_DIGEST))
    await vi.advanceTimersByTimeAsync(LONG)
    expect((await source.getSnapshot()).state).toBe('preview_ready')
    expect(events.length).toBeGreaterThan(stopped)
    expect(source.demo?.info().waiting).toBe('acceptance')
  })

  test('사람 확인 승인 뒤 배포 승인 대상에서 끝난다', async () => {
    const source = fullCycleSource(FAST)
    const { events } = open(source)
    await vi.advanceTimersByTimeAsync(LONG)
    await source.sendCommand(decide('ap-plan-1', PLAN_DIGEST))
    await vi.advanceTimersByTimeAsync(LONG)
    await source.sendCommand(decide('ap-acceptance-1', ACCEPTANCE_DIGEST))
    await vi.advanceTimersByTimeAsync(LONG)

    const snapshot = await source.getSnapshot()
    expect(snapshot.state).toBe('awaiting_release_approval')
    expect(events.length).toBe(buildFullCycle().events.length)
    expect(events.map((e) => e.seq)).toEqual(events.map((_, i) => i + 1))
    expect(source.demo?.info().done).toBe(true)
    expect((await source.getRelease()).state).toBe('prepared')
  })

  test('승인은 결정 사건에 명령 id를 담아 보낸다(화면의 대기 표시를 풀기 위해)', async () => {
    const source = fullCycleSource(FAST)
    const { events } = open(source)
    await vi.advanceTimersByTimeAsync(LONG)
    const receipt = await source.sendCommand(decide('ap-plan-1', PLAN_DIGEST, 'approve', 'cmd-plan-1'))
    expect(receipt).toMatchObject({ command_id: 'cmd-plan-1', status: 'accepted' })
    await vi.advanceTimersByTimeAsync(LONG)
    expect(events.find((e) => e.command_id === 'cmd-plan-1')?.event_type).toBe('approval_decided')
  })

  test.each([
    ['거절', () => decide('ap-plan-1', PLAN_DIGEST, 'reject')],
    ['다른 승인 id', () => decide('ap-other', PLAN_DIGEST)],
    ['다른 대상 해시', () => decide('ap-plan-1', fakeDigest('99'))],
    ['일시 중지', () => ({ ...decide('ap-plan-1', PLAN_DIGEST), action: 'pause', payload: {} }) as Command],
  ])('승인 지점에서 %s는 받지 않고 멈춘 채로 둔다', async (_name, make) => {
    const source = fullCycleSource(FAST)
    const { events } = open(source)
    await vi.advanceTimersByTimeAsync(LONG)
    const stopped = events.length

    await expect(source.sendCommand(make())).rejects.toMatchObject({ code: 'EXAMPLE_NOOP' })
    await vi.advanceTimersByTimeAsync(LONG)
    expect(events.length).toBe(stopped)
    expect((await source.getSnapshot()).state).toBe('awaiting_plan_approval')
  })

  test('승인 지점이 아닐 때의 승인은 받지 않는다', async () => {
    const source = fullCycleSource(FAST)
    open(source)
    await expect(source.sendCommand(decide('ap-plan-1', PLAN_DIGEST))).rejects.toMatchObject({ code: 'EXAMPLE_NOOP' })
  })

  test('다음 단계는 기다리지 않고 한 사건씩 넘기고, 승인 지점에서는 넘기지 않는다', async () => {
    const source = fullCycleSource({ startDelayMs: 60_000, eventGapMs: 60_000, stagePauseMs: 60_000 })
    const { events } = open(source)
    expect(events.length).toBe(0)

    source.demo?.next()
    expect(events.length).toBe(1)
    for (let i = 0; i < 40; i++) source.demo?.next()
    const atGate = events.length
    expect((await source.getSnapshot()).state).toBe('awaiting_plan_approval')
    expect(source.demo?.info().waiting).toBe('plan')

    source.demo?.next()
    expect(events.length).toBe(atGate)
  })

  test('연결을 닫으면 더 보내지 않고 같은 위치에서 다시 열 수 있다', async () => {
    const source = fullCycleSource(FAST)
    const first = open(source)
    await vi.advanceTimersByTimeAsync(130)
    first.close()
    const sent = first.events.length
    await vi.advanceTimersByTimeAsync(LONG)
    expect(first.events.length).toBe(sent)

    const second = open(source, sent)
    await vi.advanceTimersByTimeAsync(LONG)
    expect([...first.events, ...second.events].map((e) => e.seq)).toEqual(
      [...first.events, ...second.events].map((_, i) => i + 1),
    )
    expect((await source.getSnapshot()).state).toBe('awaiting_plan_approval')
  })

  test('서버로는 아무것도 보내지 않는다', async () => {
    const fetchSpy = vi.fn()
    const eventSource = vi.fn()
    vi.stubGlobal('fetch', fetchSpy)
    vi.stubGlobal('EventSource', eventSource)
    const source = fullCycleSource(FAST)
    open(source)
    await vi.advanceTimersByTimeAsync(LONG)
    await source.sendCommand(decide('ap-plan-1', PLAN_DIGEST))
    await vi.advanceTimersByTimeAsync(LONG)
    await source.sendCommand(decide('ap-acceptance-1', ACCEPTANCE_DIGEST))
    await vi.advanceTimersByTimeAsync(LONG)
    await source.getSnapshot()
    await source.getAcceptance()
    await source.getRelease()
    await source.getArtifact('a-spec')

    expect(fetchSpy).not.toHaveBeenCalled()
    expect(eventSource).not.toHaveBeenCalled()
    expect(source.kind).toBe('example')
    await expect(source.getRecording()).rejects.toMatchObject({ code: 'EXAMPLE_NOOP' })
  })
})

describe('작업 화면', () => {
  async function tick(ms: number): Promise<void> {
    await vi.advanceTimersByTimeAsync(ms)
    await flushPromises()
  }

  test('합성 시연 배지가 처음부터 끝까지, 대화상자가 열려 있을 때도 보인다', async () => {
    const source = fullCycleSource(FAST)
    const w = mount(RunWorkspace, { attachTo: document.body, props: { source } })
    await tick(0)
    expect(w.text()).toContain(FULL_CYCLE_BADGE)

    const seen = new Set<string>()
    for (let i = 0; i < 12; i++) {
      await tick(25)
      expect(w.text()).toContain(FULL_CYCLE_BADGE)
      expect(w.text()).not.toContain('합성 예시 · 실제 실행 아님')
      seen.add(source.demo!.info().label)
    }
    await tick(LONG)
    const open = w.findAll('button').find((b) => b.text().includes('기획 검토·승인'))
    expect(open).toBeTruthy()
    await open!.trigger('click')
    await tick(0)
    expect(w.text()).toContain(FULL_CYCLE_BADGE)
    expect(seen.size).toBeGreaterThan(1)
    w.unmount()
  })

  test('기획 승인 버튼을 누르면 구현이 이어지고 사람 확인 승인 뒤 배포 대상에서 끝난다', async () => {
    const source = fullCycleSource(FAST)
    const w = mount(RunWorkspace, { attachTo: document.body, props: { source } })
    await tick(LONG)
    expect(w.text()).toContain('기획 승인 대기')

    await w.findAll('button').find((b) => b.text().includes('기획 검토·승인'))!.trigger('click')
    await tick(0)
    await w.findAll('button').find((b) => b.text().includes('이 기획으로 구현 시작'))!.trigger('click')
    await tick(LONG)
    expect(w.text()).toContain('프리뷰 확인')
    expect(source.demo?.info().waiting).toBe('acceptance')

    await w.findAll('button').find((b) => b.text().includes('프리뷰 확인·수정 요청'))!.trigger('click')
    await tick(0)
    await w.find('button.approve').trigger('click')
    await tick(LONG)
    expect(source.demo?.info().done).toBe(true)
    expect(w.text()).toContain('배포 승인 대기')
    expect(w.text()).toContain(FULL_CYCLE_BADGE)
    w.unmount()
  })
})

describe('다음 단계 조작', () => {
  test('버튼과 N 키로 다음 단계를 보내고, 승인 대기 중에는 막힌다', async () => {
    const source = fullCycleSource({ startDelayMs: 60_000, eventGapMs: 60_000, stagePauseMs: 60_000 })
    const { events } = open(source)
    const w = mount(DemoControl, { attachTo: document.body, props: { demo: source.demo! } })
    await flushPromises()
    expect(w.text()).toContain('합성 시연')
    expect(w.get('button').text()).toContain('다음 단계')

    await w.get('button').trigger('click')
    expect(events.length).toBe(1)
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'n' }))
    expect(events.length).toBe(2)
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'n', ctrlKey: true }))
    expect(events.length).toBe(2)

    for (let i = 0; i < 40; i++) source.demo!.next()
    await flushPromises()
    expect(w.get('button').attributes('disabled')).toBeDefined()
    expect(w.text()).toContain('승인')
    const atGate = events.length
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'n' }))
    expect(events.length).toBe(atGate)
    w.unmount()
  })

  test('입력칸에 글자를 쓰는 중의 N 키는 무시한다', async () => {
    const source = fullCycleSource({ startDelayMs: 60_000, eventGapMs: 60_000, stagePauseMs: 60_000 })
    const { events } = open(source)
    const w = mount(DemoControl, { attachTo: document.body, props: { demo: source.demo! } })
    const field = document.createElement('textarea')
    document.body.append(field)
    field.focus()
    field.dispatchEvent(new KeyboardEvent('keydown', { key: 'n', bubbles: true }))
    expect(events.length).toBe(0)
    w.unmount()
  })
})

describe('진입', () => {
  const api = { connect: vi.fn().mockRejectedValue(new Error('no server')), getRuntime: vi.fn(), listReplays: vi.fn() }

  test('시작 화면의 다른 방법에서 전체 과정 시연을 열 수 있다', async () => {
    const w = mount(StartScreen, { attachTo: document.body, props: { api: api as never } })
    await flushPromises()
    await w.get('button.more').trigger('click')
    await flushPromises()
    const start = w.findAll('button').find((b) => b.text().includes('전체 과정 시연'))
    expect(start).toBeTruthy()
    await start!.trigger('click')
    expect(w.emitted('openExample')?.[0]?.[0]).toBe(FULL_CYCLE_ID)
    w.unmount()
  })

  test('주소 ?example=full-cycle로 바로 열면 합성 시연이 시작된다', async () => {
    window.history.replaceState(null, '', `/?example=${FULL_CYCLE_ID}`)
    const w = mount(App, { attachTo: document.body })
    await flushPromises()
    await vi.advanceTimersByTimeAsync(0)
    await flushPromises()
    expect(w.text()).toContain(FULL_CYCLE_BADGE)
    w.unmount()
  })
})
