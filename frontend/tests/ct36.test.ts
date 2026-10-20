// CT36: 같은 명세의 수정·재검토, 조회 지연·실패 뒤 옛 충족 판정이 남지 않게
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeAll, describe, expect, test, vi } from 'vitest'
import { ApiError } from '../src/api/errors'
import type { RunSource, StreamHandlers } from '../src/api/source'
import type { AcceptanceStatus, Snapshot } from '../src/api/types'
import AcceptanceList from '../src/components/AcceptanceList.vue'
import RunWorkspace from '../src/components/RunWorkspace.vue'
import { useRun } from '../src/composables/useRun'
import { SPEC_V1 } from '../src/examples/base'
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
})

const flush = async () => {
  await flushPromises()
  await new Promise((r) => setTimeout(r, 0))
  await flushPromises()
}

// 리뷰 통과 뒤의 스냅샷(검증 보고서 rp-validator 있음)
const reviewed = findScenario('preview')!.snapshot
const MET: AcceptanceStatus = { spec_version_id: SPEC_V1, items: [{ id: 'AC-2', status: 'met', report_id: 'rp-validator' }] }

function fake(initial: Snapshot) {
  let current = initial
  let pendingAcceptance: Array<(a: AcceptanceStatus) => void> = []
  let failNext = false
  let auto: AcceptanceStatus | null = MET
  const source: RunSource & { set(s: Snapshot): void; failNext(): void; manual(): void; resolve(a: AcceptanceStatus): void } = {
    kind: 'live',
    runId: initial.run_id,
    getSnapshot: vi.fn(async () => current),
    getRecording: vi.fn(),
    getAcceptance: vi.fn(() => {
      if (failNext) {
        failNext = false
        return Promise.reject(new ApiError(503, 'TEMPORARILY_UNAVAILABLE', '판정 서비스 점검'))
      }
      if (auto) return Promise.resolve(auto)
      return new Promise<AcceptanceStatus>((r) => pendingAcceptance.push(r))
    }),
    openEvents: vi.fn((_a: number, _h: StreamHandlers) => () => {}),
    sendCommand: vi.fn(),
    getArtifact: vi.fn(),
    getEnvironment: vi.fn(),
    set: (s) => { current = s },
    failNext: () => { failNext = true },
    manual: () => { auto = null },
    resolve: (a) => {
      const all = pendingAcceptance
      pendingAcceptance = []
      all.forEach((r) => r(a))
    },
  }
  return source
}

describe('CT36 판정은 현재 스냅샷 버전에 묶인다', () => {
  test('같은 명세에서 수정 Sprint로 보고서가 비면, 새 판정이 오기 전까지 옛 충족을 보이지 않는다', async () => {
    const source = fake({ ...reviewed, state_version: 10 })
    const run = useRun(source)
    await run.start()
    await flush()
    expect(run.acceptance.value?.items[0].status).toBe('met')

    // 서버의 스타일 수정: 같은 명세, reports=[], 상태 building, 버전 증가. 새 판정 조회는 지연
    source.manual()
    source.set({ ...reviewed, state: 'building', reports: [], state_version: 11 })
    await run.refreshSnapshot()
    await flush()
    expect(run.snapshot.value?.spec_version_id).toBe(SPEC_V1)
    expect(run.acceptance.value).toBeNull()
    expect(run.acceptancePending.value).toBe(true)

    // 늦게 온 응답이 옛 met를 그대로 주더라도, 현재 보고서에 근거가 없으면 무효로 표시
    source.resolve(MET)
    await flush()
    const index = acIndex(run.acceptance.value)
    expect(acView(index, 'AC-2', new Set(run.snapshot.value!.reports.map((r) => r.id))).state).toBe('stale')
    run.dispose()
  })

  test('옛 버전을 위해 시작한 조회가 늦게 도착하면 현재 버전 판정으로 쓰지 않는다', async () => {
    const source = fake({ ...reviewed, state_version: 20 })
    source.manual()
    const run = useRun(source)
    await run.start()
    // 버전 20용 조회가 아직 진행 중에 21로 바뀐다
    source.set({ ...reviewed, state_version: 21 })
    await run.refreshSnapshot()
    source.resolve(MET) // 20·21 조회가 함께 끝나도 마지막(21) 요청만 반영
    await flush()
    expect(run.acceptance.value?.items[0].status).toBe('met')
    // 22로 바뀌었는데 새 조회가 오지 않으면 표시하지 않는다
    source.set({ ...reviewed, state_version: 22 })
    await run.refreshSnapshot()
    await flush()
    expect(run.acceptance.value).toBeNull()
    run.dispose()
  })

  test('조회가 실패하면 이전 충족을 지우고 오류만 남긴다', async () => {
    const source = fake({ ...reviewed, state_version: 30 })
    const run = useRun(source)
    await run.start()
    await flush()
    expect(run.acceptance.value).not.toBeNull()
    source.failNext()
    await run.refreshAcceptance()
    expect(run.acceptance.value).toBeNull()
    expect(run.acceptanceError.value?.code).toBe('TEMPORARILY_UNAVAILABLE')
    expect(run.acceptancePending.value).toBe(false)
    run.dispose()
  })
})

describe('CT36 근거 없는 충족은 충족으로 세지 않는다', () => {
  const index = acIndex({
    spec_version_id: SPEC_V1,
    items: [
      { id: 'A', status: 'met', report_id: 'gone' },
      { id: 'B', status: 'met' },
      { id: 'C', status: 'met', report_id: 'rp-validator' },
      { id: 'D', status: 'unmet' },
    ],
  })
  const current = new Set(['rp-validator'])

  test('근거 보고서가 현재 회차에 없거나 근거가 없으면 무효', () => {
    expect(acView(index, 'A', current).state).toBe('stale')
    expect(acView(index, 'B', current).state).toBe('stale')
    expect(acView(index, 'C', current).state).toBe('met')
    expect(acView(index, 'D', current).state).toBe('unmet')
    expect(tallyAc(index, ['A', 'B', 'C', 'D'], current)).toMatchObject({ met: 1, stale: 2, unmet: 1 })
  })

  test('목록은 무효 판정을 충족으로 보이지 않고 이유를 적는다', () => {
    const w = mount(AcceptanceList, { props: { ids: ['A', 'C'], index, reports: reviewed.reports } })
    const text = w.text()
    expect(text).toContain('근거 없음(무효)')
    expect(text).toContain('현재 회차에 근거 보고서가 없어 충족으로 보지 않음')
    expect(text.match(/✓ 충족/g)).toHaveLength(1)
  })

  test('근거 패널에도 판정 실패 안내가 전달된다', async () => {
    const scenario = findScenario('review-split')!
    const source = { ...exampleSource(scenario), getAcceptance: vi.fn().mockRejectedValue(new ApiError(503, 'TEMPORARILY_UNAVAILABLE', '판정 서비스 점검')) }
    const w = mount(RunWorkspace, { attachTo: document.body, props: { source } })
    await flush()
    await w.findAll('button').find((b) => b.text().includes('상태 변경 입력 검증 보완'))!.trigger('click')
    await flush()
    expect(w.find('aside.evidence').text()).toContain('AC 판정을 읽지 못했습니다: 판정 서비스 점검 (이전 판정은 쓰지 않음)')
    w.unmount()
  })
})
