// 코드 리뷰(H1, M1–M4, M6, M7, L1, L7) 회귀 테스트
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeAll, describe, expect, test, vi } from 'vitest'
import { ApiError } from '../src/api/errors'
import type { LiveApi } from '../src/api/live'
import type { RunSource, StreamHandlers } from '../src/api/source'
import type { Snapshot } from '../src/api/types'
import BaseDialog from '../src/components/BaseDialog.vue'
import EventLog from '../src/components/EventLog.vue'
import PlanApprovalDialog from '../src/components/PlanApprovalDialog.vue'
import StartScreen from '../src/components/StartScreen.vue'
import StopDialog from '../src/components/StopDialog.vue'
import { useRun } from '../src/composables/useRun'
import { buildEvents, fakeDigest, PLAN_VIEW } from '../src/examples/base'
import { exampleSource } from '../src/examples/exampleSource'
import { findScenario } from '../src/examples/scenarios'
import { pendingApproval } from '../src/model/derive'
import { isPlanView } from '../src/model/planView'
import { groupRepeats, keepWhenFiltered } from '../src/model/relevance'

beforeAll(() => {
  const proto = HTMLDialogElement.prototype as HTMLDialogElement & { showModal(): void }
  if (!proto.showModal) proto.showModal = function (this: HTMLDialogElement) { this.setAttribute('open', '') }
})
afterEach(() => {
  vi.useRealTimers()
  sessionStorage.clear()
  document.body.innerHTML = ''
})

const flush = async () => {
  await flushPromises()
  await new Promise((r) => setTimeout(r, 0))
}
const base = findScenario('building')!.snapshot

function controllable(initial: Snapshot) {
  let current = initial
  let failing = false
  const streams: Array<{ after: number; handlers: StreamHandlers }> = []
  const source: RunSource & { set(s: Snapshot): void; fail(v: boolean): void } = {
    kind: 'live',
    runId: initial.run_id,
    getSnapshot: vi.fn(async () => {
      if (failing) throw new ApiError(0, 'NETWORK', 'down')
      return current
    }),
    getRecording: vi.fn(),
    getAcceptance: vi.fn(async () => ({ spec_version_id: current.spec_version_id, items: [] })),
    openEvents: vi.fn((after: number, handlers: StreamHandlers) => {
      streams.push({ after, handlers })
      return () => {}
    }),
    sendCommand: vi.fn(async (c) => ({ command_id: c.command_id, run_id: c.run_id, status: 'accepted' as const, accepted_at: 'x' })),
    getArtifact: vi.fn(),
    getEnvironment: vi.fn(),
    set: (s) => { current = s },
    fail: (v) => { failing = v },
  }
  return { source, streams }
}

describe('H1 사건 기록은 실패·판정 사건을 숨기지 않는다', () => {
  test('강조 항목만 필터에서도 작업 종료·검토 제출·상태 변경은 남는다', () => {
    const [finished, review, state, tool] = buildEvents([
      ['task_finished', '백엔드 실패', { task_id: 't-api' }],
      ['review_submitted', '보안 실패', { task_id: 't-security' }],
      ['run_state_changed', '실패', {}],
      ['tool_finished', '정적 검사', { task_id: 't-api' }],
    ])
    const none = new Set<string>()
    expect([finished, review, state].every((e) => keepWhenFiltered(e, none))).toBe(true)
    expect(keepWhenFiltered(tool, none)).toBe(false)
    expect(keepWhenFiltered(tool, new Set(['t-api']))).toBe(true)
  })

  test('연속 검토 제출은 묶지 않아 앞선 불합격이 가려지지 않는다', () => {
    const events = buildEvents([
      ['review_submitted', '보안 실패', { task_id: 't-security' }],
      ['review_submitted', '보안 통과', { task_id: 't-security' }],
      ['tool_finished', 'a', { task_id: 't-api' }],
      ['tool_finished', 'b', { task_id: 't-api' }],
    ])
    expect(groupRepeats(events).map((g) => g.count)).toEqual([1, 1, 2])
  })

  test('필터를 켜도 다른 분야의 실패 종료 사건이 화면에 남는다', async () => {
    const events = buildEvents([
      ['task_finished', '백엔드 작업 실패', { task_id: 't-api' }],
      ['tool_finished', '백엔드 정적 검사', { task_id: 't-api' }],
    ])
    const w = mount(EventLog, { props: { events, tasks: base.tasks } })
    await w.findAll('button').find((b) => b.text() === '출시')!.trigger('click')
    await w.find('input[type=checkbox]').setValue(true)
    expect(w.text()).toContain('백엔드 작업 실패')
    expect(w.text()).not.toContain('백엔드 정적 검사')
  })
})

describe('M1 재생은 승인 화면도 읽기 전용', () => {
  test('readOnly이면 결정 버튼 없이 안내만 보인다', async () => {
    const s = findScenario('plan-approval')!
    const w = mount(PlanApprovalDialog, {
      attachTo: document.body,
      props: { open: true, approval: pendingApproval(s.snapshot, 'plan'), specArtifactId: 'a-spec', source: exampleSource(s), runId: 'r', readOnly: true, send: vi.fn() },
    })
    await flush()
    expect(w.text()).toContain('실제 기록 재생은 읽기 전용')
    expect(w.findAll('button').map((b) => b.text())).toEqual(['닫기'])
    w.unmount()
  })
})

describe('M2 명령 ID는 결정마다 새로 만든다', () => {
  test('재개 실패 뒤 취소를 열면 이전 오류가 사라지고 다른 ID로 보낸다', async () => {
    const ids: string[] = []
    const send = vi.fn(async (_input: unknown, id: string) => {
      ids.push(id)
      return new ApiError(0, 'NETWORK', '끊김')
    })
    const w = mount(StopDialog, { attachTo: document.body, props: { open: true, action: 'resume', send } })
    await flush()
    await w.findAll('button').find((b) => b.text() === '재개')!.trigger('click')
    await flush()
    expect(w.text()).toContain('끊김')
    await w.setProps({ action: 'cancel' })
    await flush()
    expect(w.text()).not.toContain('끊김')
    await w.findAll('button').find((b) => b.text() === '실행 취소')!.trigger('click')
    await flush()
    expect(ids[0]).not.toBe(ids[1])
    w.unmount()
  })

  test('409 뒤 승인 대상이 바뀌어도 원인 안내는 남고 ID는 새로 만든다', async () => {
    const s = findScenario('plan-approval')!
    const ids: string[] = []
    const send = vi.fn(async (_i: unknown, id: string): Promise<ApiError | null> => {
      ids.push(id)
      return new ApiError(409, 'STALE_APPROVAL', '대상 변경')
    })
    const approval = pendingApproval(s.snapshot, 'plan')!
    const w = mount(PlanApprovalDialog, {
      attachTo: document.body,
      props: { open: true, approval, specArtifactId: 'a-spec', source: exampleSource(s), runId: 'r', readOnly: false, send },
    })
    await flush()
    await w.findAll('button').find((b) => b.text().includes('이 기획으로 구현 시작'))!.trigger('click')
    await flush()
    await w.setProps({ approval: { ...approval, target_digest: fakeDigest('d9') } })
    await flush()
    expect(w.text()).toContain('대상 변경')
    await w.findAll('button').find((b) => b.text().includes('이 기획으로 구현 시작'))!.trigger('click')
    await flush()
    expect(ids[1]).not.toBe(ids[0])
    expect((send.mock.calls[1][0] as { payload: { target_digest: string } }).payload.target_digest).toBe(fakeDigest('d9'))
    w.unmount()
  })
})

describe('M3 접수된 명령의 확인', () => {
  test('같은 명령 ID의 사건이 오면 확인 중 표시를 푼다', async () => {
    const { source, streams } = controllable({ ...base, state_version: 3, last_event_seq: 0 })
    const run = useRun(source)
    await run.start()
    await run.send({ action: 'pause', payload: {} }, 'cmd-x')
    expect(run.pending.value?.receipt).toBeTruthy()
    streams[0].handlers.onEvent({ ...buildEvents([['run_state_changed', 'paused', {}]])[0], state_version: 3, command_id: 'cmd-x' })
    expect(run.pending.value).toBeNull()
    run.dispose()
  })

  test('다른 작업 때문에 state_version이 올라도 내 명령의 확인 표시는 유지된다', async () => {
    const { source, streams } = controllable({ ...base, state_version: 3, last_event_seq: 0 })
    const run = useRun(source)
    await run.start()
    await run.send({ action: 'pause', payload: {} }, 'cmd-mine')
    // 워커의 무관한 작업 사건(다른 command_id 또는 없음)과 그에 따른 새 스냅샷
    source.set({ ...base, state_version: 4, last_event_seq: 1 })
    streams[0].handlers.onEvent({ ...buildEvents([['task_finished', '워커 작업 종료', { task_id: 't-api' }]])[0], state_version: 4 })
    await flush()
    expect(run.snapshot.value?.state_version).toBe(4)
    expect(run.pending.value?.commandId).toBe('cmd-mine')
    streams[0].handlers.onEvent({ ...buildEvents([['run_state_changed', '다른 명령', {}]], 2)[0], state_version: 5, command_id: 'cmd-other' })
    await flush()
    expect(run.pending.value?.commandId).toBe('cmd-mine')
    run.dispose()
  })

  test('반영 근거가 오지 않으면 일정 시간 뒤 조작을 풀고 미확인을 알린다', async () => {
    vi.useFakeTimers()
    const { source } = controllable({ ...base, state_version: 3 })
    const run = useRun(source)
    await run.start()
    await run.send({ action: 'pause', payload: {} }, 'cmd-y')
    await vi.advanceTimersByTimeAsync(20_000)
    expect(run.pending.value).toBeNull()
    expect(run.notice.value).toContain('반영을 아직 확인하지 못했습니다')
    run.dispose()
  })
})

describe('M4·L1 재연결과 재동기화', () => {
  test('다시 연결은 스냅샷을 먼저 읽고, 실패하면 스트림을 열지 않는다', async () => {
    const { source, streams } = controllable(base)
    const run = useRun(source)
    await run.start()
    source.fail(true)
    await run.reconnect()
    expect(streams).toHaveLength(1)
    expect(run.connection.value).toBe('closed')
    source.fail(false)
    await run.reconnect()
    expect(streams).toHaveLength(2)
  })

  test('resync는 새 커서 이후의 오래된 사건을 버리고, 스냅샷 실패 시 낡은 커서로 연결하지 않는다', async () => {
    const { source, streams } = controllable({ ...base, state_version: 0, last_event_seq: 0 })
    const run = useRun(source)
    await run.start()
    buildEvents([['warning', 'a', {}], ['warning', 'b', {}], ['warning', 'c', {}]], 1, 0).forEach((e) => streams[0].handlers.onEvent(e))
    source.set({ ...base, state_version: 1, last_event_seq: 1 })
    streams[0].handlers.onResync()
    await flush()
    expect(run.events.value.map((e) => e.seq)).toEqual([1])
    expect(streams.at(-1)?.after).toBe(1)

    source.fail(true)
    const before = streams.length
    streams.at(-1)!.handlers.onResync()
    await flush()
    expect(streams).toHaveLength(before)
    expect(run.connection.value).toBe('closed')
  })
})

describe('M6 포커스 복귀', () => {
  test('여는 버튼이 사라졌으면 작업 공간 본문으로 돌아간다', async () => {
    document.body.innerHTML = '<main id="workspace-main" tabindex="-1"></main><button id="opener">열기</button>'
    const opener = document.getElementById('opener') as HTMLButtonElement
    opener.focus()
    const w = mount(BaseDialog, { attachTo: document.body, props: { open: true, title: 't' } })
    await flush()
    opener.remove()
    w.find('dialog').element.dispatchEvent(new Event('close'))
    expect(document.activeElement?.id).toBe('workspace-main')
    w.unmount()
  })
})

describe('M7 기획 본문 검증', () => {
  test('필수 필드가 빠지면 PlanView로 인정하지 않는다', () => {
    expect(isPlanView(PLAN_VIEW)).toBe(true)
    expect(isPlanView({ ...PLAN_VIEW, features: undefined })).toBe(false)
    expect(isPlanView({ ...PLAN_VIEW, acceptance: [{ id: 'A' }] })).toBe(false)
    expect(isPlanView({ ...PLAN_VIEW, repository: { url: 1 } })).toBe(false)
    expect(isPlanView({ ...PLAN_VIEW, deployment: { id: 'x' } })).toBe(false)
    expect(isPlanView({ ...PLAN_VIEW, contract_digests: null })).toBe(false)
    expect(isPlanView(null)).toBe(false)
  })

  test('형식이 다른 기획 본문은 승인 버튼을 막는다', async () => {
    const s = findScenario('plan-approval')!
    const w = mount(PlanApprovalDialog, {
      attachTo: document.body,
      props: { open: true, approval: pendingApproval(s.snapshot, 'plan'), specArtifactId: 'a-spec', source: exampleSource({ ...s, artifactBodies: { 'a-spec': { goal: 'x' } } }), runId: 'r', readOnly: false, send: vi.fn() },
    })
    await flush()
    expect(w.text()).toContain('기획 본문 형식이 계약(PlanView)과 맞지 않습니다')
    expect(w.findAll('button').find((b) => b.text().includes('이 기획으로 구현 시작'))!.attributes('disabled')).toBeDefined()
    w.unmount()
  })
})

describe('L7 시작 화면 중복 생성 방지', () => {
  test('실행 생성만 실패했으면 재시도에서 같은 프로젝트를 다시 쓴다', async () => {
    const createRun = vi.fn().mockRejectedValueOnce(new ApiError(503, 'TEMPORARILY_UNAVAILABLE', '잠시')).mockResolvedValue({ run_id: 'r9' })
    const api = {
      connect: vi.fn(async () => {}),
      getRuntime: vi.fn(async () => ({ protocol_version: 1, live_available: true, provider: 'ollama_local', model: 'q', model_status: 'ready', runner_status: 'ready', inference_slots: 1, external_api_enabled: false, deployment_enabled: false, reasons: [] })),
      listReplays: vi.fn(async () => []),
      createProject: vi.fn(async () => ({ project_id: 'p1', title: 't', created_at: 'x' })),
      createRun,
    } as unknown as LiveApi
    const w = mount(StartScreen, { attachTo: document.body, props: { api } })
    await flush()
    await w.find('textarea').setValue('r')
    await w.find('form').trigger('submit')
    await flush()
    await w.find('form').trigger('submit')
    await flush()
    expect(api.createProject).toHaveBeenCalledOnce()
    expect(createRun).toHaveBeenCalledTimes(2)
    expect((w.emitted('openRun') as unknown[][])[0][0]).toBe('r9')
  })
})
