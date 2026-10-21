// CR-C15 출시·복구 결과(ReleaseView)와 Runtime 템플릿 보조 정보. 계약: Codex 8ff4ca1 → a6eb8a4(원래 요청 번호 유지).
// Runtime 템플릿 상태는 CR-C14(기획별 지원 공백)를 대신하지 않는다 — CR-C14는 plan-support.test.ts.
import Ajv2020 from 'ajv/dist/2020'
import addFormats from 'ajv-formats'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeAll, describe, expect, test, vi } from 'vitest'
import { LiveApi } from '../src/api/live'
import type { ReleaseView, Runtime } from '../src/api/types'
import ReleaseApprovalDialog from '../src/components/ReleaseApprovalDialog.vue'
import ReleasePanel from '../src/components/ReleasePanel.vue'
import RunWorkspace from '../src/components/RunWorkspace.vue'
import StartScreen from '../src/components/StartScreen.vue'
import { buildEvents, fakeDigest } from '../src/examples/base'
import { exampleSource } from '../src/examples/exampleSource'
import { SCENARIOS, findScenario } from '../src/examples/scenarios'
import { pendingApproval } from '../src/model/derive'
import { isReleaseView } from '../src/model/release'

beforeAll(() => {
  const proto = HTMLDialogElement.prototype as HTMLDialogElement & { showModal(): void }
  if (!proto.showModal) proto.showModal = function (this: HTMLDialogElement) { this.setAttribute('open', '') }
  if (!('ResizeObserver' in globalThis)) {
    ;(globalThis as Record<string, unknown>).ResizeObserver = class { observe() {} disconnect() {} }
  }
})
afterEach(() => {
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})

const flush = async () => {
  await flushPromises()
  await new Promise((r) => setTimeout(r, 120))
  await flushPromises()
}

const dir = resolve(__dirname, '../../docs/planning')
const ajv = new Ajv2020({ strict: false, allErrors: true })
addFormats(ajv)
ajv.addSchema(JSON.parse(readFileSync(resolve(dir, 'protocol.v1.schema.json'), 'utf8')), 'protocol.v1.schema.json')
ajv.addSchema(JSON.parse(readFileSync(resolve(dir, 'http.v1.schema.json'), 'utf8')), 'http.v1.schema.json')
const validRelease = (v: unknown) => ajv.getSchema('http.v1.schema.json#/$defs/ReleaseView')!(v)
const validRuntime = (v: unknown) => ajv.getSchema('http.v1.schema.json#/$defs/Runtime')!(v)

const approvalScenario = findScenario('release-approval')!
const doneScenario = findScenario('succeeded')!
const prepared = approvalScenario.release!
const op = (action: 'push' | 'deploy' | 'rollback', state: ReleaseView['operations'][number]['state'], n: string, extra: Partial<ReleaseView['operations'][number]> = {}) =>
  ({ operation_id: fakeDigest(n), action, state, accepted_at: '2026-10-21T01:00:00Z', observed_at: null, reason: '조회 대기', volume_preserved: null, ...extra })

describe('합성 ReleaseView는 계약을 따른다', () => {
  test('모든 예시의 출시 보기가 스키마와 가드를 통과한다', async () => {
    for (const s of SCENARIOS) {
      const view = await exampleSource(s).getRelease()
      expect(validRelease(view)).toBe(true)
      expect(isReleaseView(view)).toBe(true)
      expect(view.run_id).toBe(s.snapshot.run_id)
    }
  })

  test('계약 밖 값은 가드가 거절한다', () => {
    expect(isReleaseView({ ...prepared, enabled: true })).toBe(false)
    expect(isReleaseView({ ...prepared, state: 'deployed' })).toBe(false)
    expect(isReleaseView({ ...prepared, operations: [op('rollback', 'applied', 'a1'), { ...op('push', 'applied', 'a2'), action: 'restore' }] })).toBe(false)
    expect(isReleaseView({ ...prepared, operations: [{ ...op('push', 'applied', 'a2'), reason: '' }] })).toBe(false)
    expect(isReleaseView({ ...prepared, operations: [{ ...op('push', 'pending' as never, 'a2') }] })).toBe(false) // 정정 계약에서 pending → accepted
    expect(isReleaseView({ ...prepared, operations: [{ ...op('rollback', 'applied', 'a2'), volume_preserved: 'yes' }] })).toBe(false)
    expect(isReleaseView({ ...prepared, reason: '' })).toBe(false)
    expect(isReleaseView(null)).toBe(false)
  })
})

describe('LiveApi 출시 보기', () => {
  test('GET /api/runs/{id}/release로 읽는다(읽기 전용, CSRF 불필요)', async () => {
    const fetchFn = vi.fn(async () => new Response(JSON.stringify(prepared), { status: 200 }))
    const api = new LiveApi(fetchFn as unknown as typeof fetch, () => ({}) as EventSource)
    await expect(api.getRelease('run-1')).resolves.toMatchObject({ enabled: false })
    expect((fetchFn.mock.calls[0] as unknown[])[0]).toBe('/api/runs/run-1/release')
    expect(((fetchFn.mock.calls[0] as unknown[])[1] as RequestInit).method).toBe('GET')
  })
})

describe('출시·복구 패널(읽기 전용)', () => {
  const panel = (view: unknown, kind: 'live' | 'example' = 'live') => mount(ReleasePanel, { props: { view, error: null, kind } }).text()

  test('실행 비활성과 미설정 이유를 보여 준다', () => {
    const text = panel({ run_id: 'r', enabled: false, state: 'unconfigured', target: null, details: null, operations: [], reason: '등록된 출시 manifest가 없습니다.' })
    expect(text).toContain('실제 출시 실행 비활성')
    expect(text).toContain('출시 대상 미설정')
    expect(text).toContain('등록된 출시 manifest가 없습니다.')
  })

  test('준비된 대상은 저장소·자동 배포 여부·환경·이미지·무료 정책·복구 계획을 보여 준다', () => {
    const text = panel(prepared)
    expect(text).toContain('준비됨 · 실행하지 않음')
    expect(text).toContain(prepared.details!.repository.url)
    expect(text).toContain('push 시 자동 배포 없음')
    expect(text).toContain('스테이징 (합성)')
    expect(text).toContain(prepared.details!.image_reference)
    expect(text).toContain('첫 출시 공개 중단 · 데이터 볼륨 보존 · 스키마 이전 없음')
  })

  test('push가 자동 배포를 일으키면 경고한다', () => {
    const view = { ...prepared, details: { ...prepared.details!, repository: { ...prepared.details!.repository, auto_deploy: true } } }
    expect(panel(view)).toContain('push하면 자동 배포가 일어납니다')
  })

  test('의도 기록·확인된 결과·불명을 구분하고, 복구를 이전 버전 복원으로 표시하지 않는다', () => {
    const accepted = panel({ ...prepared, state: 'accepted', operations: [op('push', 'accepted', 'b1')] })
    expect(accepted).toContain('실행 의도 기록 · 결과 미확인')
    expect(accepted).toContain('실제 조회 기록 없음') // observed_at=null을 조회 시각으로 만들지 않는다
    const uncertain = panel({ ...prepared, state: 'uncertain', operations: [op('push', 'applied', 'b1'), op('deploy', 'uncertain', 'b2')] })
    expect(uncertain).toContain('결과 불명 · 자동 재실행 안 함')
    expect(uncertain).toContain('확인된 결과')
    const rolled = panel({ ...prepared, state: 'rolled_back', operations: [op('deploy', 'applied', 'b2'), op('rollback', 'rolled_back', 'b3')] })
    expect(rolled).toContain('첫 출시 공개 중단')
    expect(rolled).toContain('이전 버전 복원이 아닙니다')
    expect(rolled).toContain('볼륨 보존 미확인') // volume_preserved=null은 보존으로 추정하지 않는다
    const checked = panel({ ...prepared, state: 'rolled_back', operations: [op('rollback', 'rolled_back', 'b3', { observed_at: '2026-10-21T01:02:00Z', volume_preserved: true })] })
    expect(checked).toContain('볼륨 보존 조회 확인(데이터 내용 검증 아님)')
    expect(panel({ ...prepared, state: 'failed', operations: [op('deploy', 'failed', 'b4', { reason: '상태 확인 실패' })] })).toContain('상태 확인 실패')
    expect(panel({ ...prepared, state: 'not_applied' })).toContain('성공이 아닙니다')
  })

  test('합성 예시는 합성으로, 형식이 틀린 본문은 표시하지 않는다', () => {
    expect(panel(prepared, 'example')).toContain('합성 예시')
    expect(panel({ ...prepared, state: 'deployed' })).toContain('출시 정보 형식이 계약과 맞지 않아 표시하지 않습니다')
  })
})

describe('enabled=false에서는 배포 승인을 보내지 않는다', () => {
  test('승인·거절 버튼 없이 대상만 확인하게 한다', async () => {
    const send = vi.fn()
    const w = mount(ReleaseApprovalDialog, {
      attachTo: document.body,
      props: { open: true, approval: pendingApproval(approvalScenario.snapshot, 'release'), snapshot: approvalScenario.snapshot, source: exampleSource(approvalScenario), readOnly: false, releaseEnabled: false, send },
    })
    await flushPromises()
    const labels = w.findAll('button').map((b) => b.text())
    expect(labels.some((t) => t.includes('배포 승인'))).toBe(false)
    expect(labels.some((t) => t.includes('배포 거절'))).toBe(false)
    expect(w.text()).toContain('서버가 실제 출시 실행을 비활성으로 알립니다')
    expect(send).not.toHaveBeenCalled()
    w.unmount()
  })
})

describe('작업 화면 연결', () => {
  test('출시 패널을 표시하고, 배포 사건이 오면 다시 읽는다', async () => {
    const base = exampleSource(doneScenario)
    const getRelease = vi.fn(base.getRelease)
    const w = mount(RunWorkspace, { attachTo: document.body, props: { source: { ...base, getRelease } } })
    await flush()
    expect(w.find('section[aria-label="출시·복구"]').text()).toContain('적용 확인됨')
    const calls = getRelease.mock.calls.length
    expect(calls).toBeGreaterThanOrEqual(1)
    w.unmount()
  })

  test('출시 보기 조회 실패는 원인을 보여 준다', async () => {
    const base = exampleSource(approvalScenario)
    const w = mount(RunWorkspace, { attachTo: document.body, props: { source: { ...base, getRelease: vi.fn().mockRejectedValue(new Error('x')) } } })
    await flush()
    expect(w.find('section[aria-label="출시·복구"]').text()).toContain('출시 정보를 읽지 못했습니다')
    w.unmount()
  })

  test('배포 사건(deployment_*·operation_uncertain)이 오면 출시 보기를 다시 읽는다', async () => {
    const base = exampleSource(approvalScenario)
    const getRelease = vi.fn(base.getRelease)
    let push: ((e: unknown) => void) | null = null
    const source = {
      ...base,
      getRelease,
      openEvents: (after: number, h: Parameters<typeof base.openEvents>[1]) => {
        const close = base.openEvents(after, h)
        push = (e) => h.onEvent(e as never)
        return close
      },
    }
    const w = mount(RunWorkspace, { attachTo: document.body, props: { source } })
    await flush()
    const before = getRelease.mock.calls.length
    const last = approvalScenario.snapshot
    const tailCount = approvalScenario.events.length
    const event = buildEvents([['operation_uncertain', '배포 결과 불명', {}]], tailCount + 1, last.state_version)[0]
    push!({ ...event, state_version: last.state_version })
    await flush()
    expect(getRelease.mock.calls.length).toBeGreaterThan(before)
    w.unmount()
  })
})

describe('Runtime 템플릿·외부 데이터 안내', () => {
  const runtime = (extra: Partial<Runtime>): Runtime => ({
    protocol_version: 1, live_available: true, provider: 'ollama_local', model: 'qwen3.5:4b', model_status: 'ready', runner_status: 'ready',
    inference_slots: 1, external_api_enabled: false, deployment_enabled: false, reasons: [], ...extra,
  })
  const start = async (rt: Runtime) => {
    expect(validRuntime(rt)).toBe(true)
    const api = { connect: vi.fn(async () => {}), getRuntime: vi.fn(async () => rt), listReplays: vi.fn(async () => []) }
    const w = mount(StartScreen, { attachTo: document.body, props: { api: api as never } })
    await flush()
    return w
  }

  test('외부 데이터 미설정이면 과제 이름 없이 범용 안내와 서버 사유를 그대로 보여 준다', async () => {
    const reason = '서버 사유: 외부 데이터 연결은 사용자 결정으로 보류했습니다.'
    const w = await start(runtime({ template_id: 'cafemap-v1', data_source_status: 'unconfigured', reasons: [reason] }))
    const notice = w.find('[data-testid="data-notice"]').text()
    expect(notice).toContain('외부 데이터 미설정')
    expect(notice).toContain('LIVE 가능은 로컬 모델·실행기 준비만 뜻합니다')
    expect(notice).toContain(reason)
    expect(notice).not.toContain('카공지도')
    expect(notice).not.toContain('지도')
    await w.find('button.more').trigger('click')
    await flush()
    const dialog = document.querySelector('dialog[open]')!.textContent!
    expect(dialog).toContain('템플릿')
    expect(dialog).toContain('cafemap-v1')
    expect(dialog).not.toContain('카공지도')
    expect(dialog).toContain('외부 데이터')
    expect(dialog).toContain('미설정')
    expect(dialog).not.toContain('지도')
    w.unmount()
  })

  test('외부 데이터가 필요 없는 템플릿은 경고하지 않고, 필드가 없는 옛 서버도 그대로 동작한다', async () => {
    const w = await start(runtime({ template_id: 'requests-v1', data_source_status: 'not_required' }))
    expect(w.find('[data-testid="data-notice"]').exists()).toBe(false)
    w.unmount()
    const old = await start(runtime({}))
    expect(old.find('[data-testid="data-notice"]').exists()).toBe(false)
    old.unmount()
  })
})
