import { afterEach, describe, expect, test, vi } from 'vitest'
import { ApiError } from '../src/api/errors'
import type { RunSource, StreamHandlers } from '../src/api/source'
import type { Snapshot } from '../src/api/types'
import { useRun } from '../src/composables/useRun'
import { buildEvents } from '../src/examples/base'
import { exampleSource } from '../src/examples/exampleSource'
import { findScenario } from '../src/examples/scenarios'

const base = findScenario('building')!.snapshot
const flush = () => new Promise((r) => setTimeout(r, 0))

function controllableSource(initial: Snapshot) {
  let current = initial
  const streams: Array<{ after: number; handlers: StreamHandlers; closed: boolean }> = []
  const source: RunSource & { setSnapshot(s: Snapshot): void } = {
    kind: 'live',
    runId: initial.run_id,
    getSnapshot: vi.fn(async () => current),
    openEvents: vi.fn((after: number, handlers: StreamHandlers) => {
      const stream = { after, handlers, closed: false }
      streams.push(stream)
      return () => {
        stream.closed = true
      }
    }),
    sendCommand: vi.fn(async (c) => ({ command_id: c.command_id, run_id: c.run_id, status: 'accepted' as const, accepted_at: 'x' })),
    getArtifact: vi.fn(),
    getEnvironment: vi.fn(),
    setSnapshot(s) {
      current = s
    },
  }
  return { source, streams }
}

const events = (n: number, start = 1, version = 0) =>
  buildEvents(Array.from({ length: n }, (_, i) => ['tool_finished', `e${start + i}`, {}] as const).map((s) => [...s]) as never, start, version)
    .map((e) => ({ ...e, state_version: version }))

afterEach(() => vi.useRealTimers())

describe('useRun 스트림 처리', () => {
  test('처음부터 기록을 받고 중복 seq는 한 번만 반영한다', async () => {
    const { source, streams } = controllableSource({ ...base, state_version: 0, last_event_seq: 2 })
    const run = useRun(source)
    await run.start()
    expect(streams[0].after).toBe(0)
    const [a, b] = events(2)
    streams[0].handlers.onEvent(a)
    streams[0].handlers.onEvent(a)
    streams[0].handlers.onEvent(b)
    expect(run.events.value.map((e) => e.seq)).toEqual([1, 2])
  })

  test('기록 사건은 연출하지 않고 연결 뒤 새 사건만 장면에 알린다', async () => {
    const { source, streams } = controllableSource({ ...base, state_version: 0, last_event_seq: 1 })
    const run = useRun(source)
    const seen = vi.fn()
    run.onLiveEvent(seen)
    await run.start()
    events(2).forEach((e) => streams[0].handlers.onEvent(e))
    expect(seen.mock.calls.map(([e]) => e.seq)).toEqual([2])
  })

  test('seq 누락이면 마지막 seq부터 다시 연결하고 스냅샷을 다시 읽는다', async () => {
    const { source, streams } = controllableSource({ ...base, state_version: 0, last_event_seq: 0 })
    const run = useRun(source)
    await run.start()
    const [e1, , e3] = events(3)
    streams[0].handlers.onEvent(e1)
    streams[0].handlers.onEvent(e3)
    expect(streams[0].closed).toBe(true)
    expect(streams[1].after).toBe(1)
    expect(run.connection.value).toBe('resyncing')
    expect(run.notice.value).toContain('누락')
    expect(run.events.value).toHaveLength(1)
  })

  test('resync 신호면 최신 스냅샷의 seq부터 다시 연결한다', async () => {
    const { source, streams } = controllableSource({ ...base, state_version: 0, last_event_seq: 0 })
    const run = useRun(source)
    await run.start()
    source.setSnapshot({ ...base, state_version: 4, last_event_seq: 40 })
    streams[0].handlers.onResync()
    await flush()
    expect(run.snapshot.value?.state_version).toBe(4)
    expect(streams.at(-1)?.after).toBe(40)
  })

  test('연결 끊김은 연결 상태만 바꾸고 실행 상태는 그대로 둔다', async () => {
    const { source, streams } = controllableSource(base)
    const run = useRun(source)
    await run.start()
    streams[0].handlers.onOpen()
    expect(run.connection.value).toBe('open')
    streams[0].handlers.onDown(false)
    expect(run.connection.value).toBe('reconnecting')
    streams[0].handlers.onDown(true)
    expect(run.connection.value).toBe('closed')
    expect(run.snapshot.value?.state).toBe('building')
    await run.reconnect()
    expect(streams).toHaveLength(2)
  })

  test('더 새 상태 버전 사건이 오면 스냅샷을 다시 읽고, 늦은 이전 버전은 버린다', async () => {
    const { source, streams } = controllableSource({ ...base, state_version: 1, last_event_seq: 0 })
    const run = useRun(source)
    await run.start()
    source.setSnapshot({ ...base, state_version: 2, last_event_seq: 1 })
    streams[0].handlers.onEvent(events(1, 1, 2)[0])
    await flush()
    expect(run.snapshot.value?.state_version).toBe(2)
    source.setSnapshot({ ...base, state_version: 1 })
    await run.refreshSnapshot()
    expect(run.snapshot.value?.state_version).toBe(2)
  })

  test('스냅샷을 못 읽으면 연결하지 않고 오류를 남긴다', async () => {
    const { source, streams } = controllableSource(base)
    vi.mocked(source.getSnapshot).mockRejectedValueOnce(new ApiError(404, 'NOT_FOUND', '없음'))
    const run = useRun(source)
    await run.start()
    expect(run.loadError.value?.code).toBe('NOT_FOUND')
    expect(run.connection.value).toBe('closed')
    expect(streams).toHaveLength(0)
  })
})

describe('useRun 명령', () => {
  test('현재 상태 버전으로 명령을 만들고, 202 접수 뒤에도 반영 전까지 pending을 유지한다', async () => {
    const { source } = controllableSource({ ...base, state_version: 5 })
    const run = useRun(source)
    await run.start()
    await run.send({ action: 'pause', payload: {} }, 'cmd-1')
    const sent = vi.mocked(source.sendCommand).mock.calls[0][0]
    expect(sent).toMatchObject({ kind: 'command', protocol_version: 1, command_id: 'cmd-1', expected_state_version: 5, action: 'pause', payload: {} })
    expect(run.pending.value?.receipt?.status).toBe('accepted')

    source.setSnapshot({ ...base, state_version: 6, state: 'paused' })
    await run.refreshSnapshot()
    expect(run.pending.value).toBeNull()
  })

  test('409 충돌이면 pending을 지우고 최신 스냅샷을 다시 읽은 뒤 오류를 전달한다', async () => {
    const { source } = controllableSource({ ...base, state_version: 5 })
    const run = useRun(source)
    await run.start()
    vi.mocked(source.sendCommand).mockRejectedValueOnce(new ApiError(409, 'STALE_APPROVAL', '대상 변경'))
    source.setSnapshot({ ...base, state_version: 7 })
    await expect(run.send({ action: 'resume', payload: {} }, 'cmd-2')).rejects.toMatchObject({ code: 'STALE_APPROVAL' })
    expect(run.pending.value).toBeNull()
    expect(run.snapshot.value?.state_version).toBe(7)
  })

  test('스냅샷이 없으면 명령을 보내지 않는다', async () => {
    const { source } = controllableSource(base)
    await expect(useRun(source).send({ action: 'pause', payload: {} }, 'c')).rejects.toBeInstanceOf(ApiError)
    expect(source.sendCommand).not.toHaveBeenCalled()
  })

  test('명령 ID가 같은 사건이 오면 스냅샷을 다시 읽는다', async () => {
    const { source, streams } = controllableSource({ ...base, state_version: 3, last_event_seq: 0 })
    const run = useRun(source)
    await run.start()
    await run.send({ action: 'pause', payload: {} }, 'cmd-9')
    const calls = vi.mocked(source.getSnapshot).mock.calls.length
    streams[0].handlers.onEvent({ ...events(1, 1, 3)[0], command_id: 'cmd-9' })
    await flush()
    expect(vi.mocked(source.getSnapshot).mock.calls.length).toBeGreaterThan(calls)
    run.dispose()
  })
})

describe('합성 예시 출처', () => {
  test('명령은 보내지 않고 EXAMPLE_NOOP으로 거절한다', async () => {
    const run = useRun(exampleSource(findScenario('plan-approval')!))
    await run.start()
    await expect(run.send({ action: 'pause', payload: {} }, 'c')).rejects.toMatchObject({ code: 'EXAMPLE_NOOP' })
    expect(run.isReplay.value).toBe(false)
    run.dispose()
  })

  test('기록 사건을 바로, tail 사건을 간격을 두고 흘린다', async () => {
    vi.useFakeTimers()
    const scenario = findScenario('building')!
    const run = useRun(exampleSource(scenario))
    await run.start()
    await vi.advanceTimersByTimeAsync(1)
    expect(run.events.value).toHaveLength(scenario.events.length)
    await vi.advanceTimersByTimeAsync(2600 * scenario.tail.length)
    expect(run.events.value).toHaveLength(scenario.events.length + scenario.tail.length)
    run.dispose()
  })

  test('기획 본문과 환경만 제공하고 나머지는 없음을 알린다', async () => {
    const source = exampleSource(findScenario('release-approval')!)
    await expect(source.getArtifact('a-spec')).resolves.toMatchObject({ spec_version_id: 'spec-v1' })
    await expect(source.getArtifact('a-diff-ui')).rejects.toMatchObject({ code: 'NOT_FOUND' })
    await expect(source.getEnvironment('env-staging')).resolves.toMatchObject({ exposure: 'private' })
    await expect(source.getEnvironment('nope')).rejects.toMatchObject({ code: 'NOT_FOUND' })
  })
})
