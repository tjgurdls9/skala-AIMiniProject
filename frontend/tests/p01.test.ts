// DEV-P01/S02 소비자: CR-C09 AC 판정, CR-C10 Preview, CR-C11 명령 사건 순서, CODEX-UI-001
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeAll, describe, expect, test, vi } from 'vitest'
import { ApiError } from '../src/api/errors'
import { LiveApi } from '../src/api/live'
import type { RunSource, StreamHandlers } from '../src/api/source'
import type { AcceptanceStatus, CommandReceipt, Snapshot } from '../src/api/types'
import PreviewDialog from '../src/components/PreviewDialog.vue'
import RunWorkspace from '../src/components/RunWorkspace.vue'
import { useRun } from '../src/composables/useRun'
import { buildEvents, CANDIDATE, SPEC_V1, SPEC_V2 } from '../src/examples/base'
import { exampleSource } from '../src/examples/exampleSource'
import { findScenario } from '../src/examples/scenarios'
import { acIndex, acView, tallyAc } from '../src/model/acceptance'

beforeAll(() => {
  const proto = HTMLDialogElement.prototype as HTMLDialogElement & { showModal(): void }
  if (!proto.showModal) proto.showModal = function (this: HTMLDialogElement) { this.setAttribute('open', '') }
  if (!('ResizeObserver' in globalThis)) {
    ;(globalThis as Record<string, unknown>).ResizeObserver = class { observe() {} disconnect() {} }
  }
})
afterEach(() => {
  document.body.innerHTML = ''
  vi.useRealTimers()
})

const flush = async () => {
  await flushPromises()
  await new Promise((r) => setTimeout(r, 0))
  await flushPromises()
}
const base = findScenario('building')!.snapshot

function liveFake(initial: Snapshot, acceptance: (snap: Snapshot) => Promise<AcceptanceStatus>) {
  let current = initial
  const streams: StreamHandlers[] = []
  let resolveSend: (() => void) | null = null
  const source: RunSource & { set(s: Snapshot): void; resolveSend(): void } = {
    kind: 'live',
    runId: initial.run_id,
    getSnapshot: vi.fn(async () => current),
    getAcceptance: vi.fn(() => acceptance(current)),
    openEvents: vi.fn((_after: number, h: StreamHandlers) => {
      streams.push(h)
      return () => {}
    }),
    sendCommand: vi.fn((c) => new Promise<CommandReceipt>((r) => {
      resolveSend = () => r({ command_id: c.command_id, run_id: c.run_id, status: 'accepted', accepted_at: 'x' })
    })),
    getArtifact: vi.fn(),
    getEnvironment: vi.fn(),
    set: (s) => { current = s },
    resolveSend: () => resolveSend?.(),
  }
  return { source, streams }
}

describe('CR-C09 AC 판정 소비', () => {
  test('LiveApi는 실행별 acceptance 경로를 읽는다', async () => {
    const fetchFn = vi.fn(async (_url: string) => new Response(JSON.stringify({ spec_version_id: 's', items: [] }), { status: 200 }))
    await new LiveApi(fetchFn as unknown as typeof fetch).getAcceptance('r/1')
    expect(fetchFn.mock.calls[0][0]).toBe('/api/runs/r%2F1/acceptance')
  })

  test('판정 없는 AC는 충족으로 추정하지 않고 판정 없음으로 센다', () => {
    const index = acIndex({ spec_version_id: 's', items: [{ id: 'A', status: 'met', report_id: 'rp' }, { id: 'B', status: 'failed' }] })
    expect(acView(index, 'A')).toEqual({ state: 'met', reportId: 'rp' })
    expect(acView(index, 'Z')).toEqual({ state: 'unknown' })
    expect(tallyAc(index, ['A', 'B', 'Z'])).toEqual({ met: 1, unmet: 0, failed: 1, not_run: 0, unknown: 1 })
    expect(acIndex(null).size).toBe(0)
  })

  test('늦게 도착한 옛 응답은 버리고 최신 요청의 판정만 쓴다', async () => {
    const resolvers: Array<(a: AcceptanceStatus) => void> = []
    const { source } = liveFake({ ...base, state_version: 1 }, () => new Promise((r) => resolvers.push(r)))
    const run = useRun(source)
    await run.start()
    void run.refreshAcceptance()
    resolvers[1]({ spec_version_id: SPEC_V1, items: [{ id: 'AC-2', status: 'met' }] })
    await flush()
    resolvers[0]({ spec_version_id: SPEC_V1, items: [{ id: 'AC-2', status: 'unmet' }] })
    await flush()
    expect(run.acceptance.value?.items[0].status).toBe('met')
    run.dispose()
  })

  test('명세가 바뀌면 옛 명세의 판정을 화면에 쓰지 않고 불일치를 알린다', async () => {
    const { source } = liveFake({ ...base, state_version: 1 }, async () => ({ spec_version_id: SPEC_V1, items: [{ id: 'AC-2', status: 'met' }] }))
    const run = useRun(source)
    await run.start()
    await flush()
    expect(run.acceptance.value?.items).toHaveLength(1)
    source.set({ ...base, state_version: 2, spec_version_id: SPEC_V2 })
    await run.refreshSnapshot()
    await flush()
    expect(run.acceptance.value).toBeNull()
    expect(run.acceptanceMismatch.value).toBe(true)
    run.dispose()
  })

  test('판정 읽기 실패는 오류로 남기고 이전 판정을 충족 근거로 쓰지 않는다', async () => {
    const { source } = liveFake(base, async () => { throw new ApiError(500, 'BAD_RESPONSE', '깨짐') })
    const run = useRun(source)
    await run.start()
    await flush()
    expect(run.acceptanceError.value?.message).toBe('깨짐')
    expect(run.acceptance.value).toBeNull()
    run.dispose()
  })

  test('작업 공간은 보안 실패와 기능 AC 충족을 함께, 따로 보여준다', async () => {
    const w = mount(RunWorkspace, { attachTo: document.body, props: { source: exampleSource(findScenario('review-split')!) } })
    await flush()
    await w.findAll('nav.tree button').find((b) => b.text().includes('Sprint 4'))!.trigger('click')
    await flush()
    const board = w.find('.board').text()
    expect(board).toContain('✓ 충족 3')
    expect(board).toContain('근거: 검증 보고서')
    expect(board).toContain('작업 완료 수와 별개')
    expect(w.text()).toContain('보안 실패 — 출시 차단')
    w.unmount()
  })
})

describe('CR-C11 명령 사건이 POST 응답보다 먼저 와도', () => {
  test('확인 표시를 끝내고, 뒤늦은 202가 확인 대기를 다시 만들지 않는다', async () => {
    vi.useFakeTimers()
    const { source, streams } = liveFake({ ...base, state_version: 3, last_event_seq: 0 }, async (s) => ({ spec_version_id: s.spec_version_id, items: [] }))
    const run = useRun(source)
    await run.start()
    const sending = run.send({ action: 'pause', payload: {} }, 'cmd-early')
    expect(run.pending.value?.commandId).toBe('cmd-early')
    streams[0].onEvent({ ...buildEvents([['run_state_changed', '일시 중지', {}]])[0], state_version: 4, command_id: 'cmd-early' })
    expect(run.pending.value).toBeNull()
    source.resolveSend()
    await sending
    expect(run.pending.value).toBeNull()
    await vi.advanceTimersByTimeAsync(25_000)
    expect(run.notice.value).toBeNull()
    run.dispose()
  })
})

describe('CODEX-UI-001 재생·옛 후보 프리뷰는 iframe을 만들지 않는다', () => {
  const preview = findScenario('preview')!
  // 계약상 프리뷰는 운영 화면과 다른 hostname이어야 한다. 테스트 환경 주소와 겹치지 않는 host를 쓴다
  const host = location.hostname === 'localhost' ? '127.0.0.1' : 'localhost'
  const body = { url: `http://${host}:58123/`, origin: `http://${host}:58123`, commit_sha: CANDIDATE.commit }
  const source = (snapshot: Snapshot, previewBody: unknown): RunSource => ({
    ...exampleSource(preview),
    kind: 'live',
    getSnapshot: async () => snapshot,
    getArtifact: async () => previewBody,
  })
  const open = async (snapshot: Snapshot, previewBody: unknown, readOnly: boolean) => {
    const w = mount(PreviewDialog, {
      attachTo: document.body,
      props: { open: true, snapshot, source: source(snapshot, previewBody), readOnly, selectedArtifactId: null, send: vi.fn() },
    })
    await flush()
    return w
  }

  test('LIVE 현재 후보의 프리뷰 확인 단계에서만 sandbox iframe을 연다', async () => {
    const w = await open(preview.snapshot, body, false)
    expect(w.find('iframe').exists()).toBe(true)
    w.unmount()
  })

  test('실제 기록 재생은 기록 주소·커밋만 보여준다', async () => {
    const replay: Snapshot = { ...preview.snapshot, mode: 'replay', replay_source: { source_run_id: 'old', recorded_at: '2026-10-20T00:00:00Z', manifest_digest: `sha256:${'ab'.repeat(32)}` } }
    const w = await open(replay, body, true)
    expect(w.find('iframe').exists()).toBe(false)
    expect(w.text()).toContain('실제 기록 재생에서는 외부 앱을 열지 않습니다')
    expect(w.text()).toContain(body.url)
    expect(w.text()).toContain('지금 실행 중인 앱이 아닙니다')
    w.unmount()
  })

  test('현재 후보와 다른 옛 후보·프리뷰 단계가 아닌 실행은 기록으로만 보여준다', async () => {
    const old = await open(preview.snapshot, { ...body, commit_sha: 'ef'.repeat(20) }, false)
    expect(old.find('iframe').exists()).toBe(false)
    expect(old.text()).toContain('옛 후보의 프리뷰')
    old.unmount()
    const later = await open({ ...preview.snapshot, state: 'awaiting_release_approval' }, body, false)
    expect(later.find('iframe').exists()).toBe(false)
    expect(later.text()).toContain('과거 기록으로만')
    later.unmount()
  })
})
