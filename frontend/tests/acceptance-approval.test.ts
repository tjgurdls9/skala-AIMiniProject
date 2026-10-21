// CR-C18 사람 확인 AC의 승인(gate "acceptance"). 계약: Codex db1300f.
// 승인은 사용자 조작으로만 생기며, 사람 확인 AC의 판정(not_run)은 승인으로 met가 되지 않는다.
import Ajv2020 from 'ajv/dist/2020'
import addFormats from 'ajv-formats'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeAll, describe, expect, test, vi } from 'vitest'
import type { Approval, ReleaseTarget, Snapshot } from '../src/api/types'
import AcceptanceApprovalSection from '../src/components/AcceptanceApprovalSection.vue'
import AcceptanceList from '../src/components/AcceptanceList.vue'
import PreviewDialog from '../src/components/PreviewDialog.vue'
import ReleaseApprovalDialog from '../src/components/ReleaseApprovalDialog.vue'
import RunWorkspace from '../src/components/RunWorkspace.vue'
import { CANDIDATE, fakeDigest, report } from '../src/examples/base'
import { exampleSource } from '../src/examples/exampleSource'
import { SCENARIOS, findScenario } from '../src/examples/scenarios'
import {
  acceptanceApprovals,
  acceptanceMismatch,
  currentAcceptance,
  manualAcStates,
  manualPendingOf,
  releaseAcceptanceGate,
} from '../src/model/acceptanceApproval'
import { runAlerts } from '../src/model/alerts'
import { reviewPair } from '../src/model/derive'

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
const validApproval = (v: unknown) => ajv.getSchema('protocol.v1.schema.json#/$defs/Approval')!(v)
const validSnapshot = (v: unknown) => ajv.getSchema('protocol.v1.schema.json#/$defs/Snapshot')!(v)

const previewScenario = findScenario('preview')!
const releaseScenario = findScenario('release-approval')!
const doneScenario = findScenario('succeeded')!

type AcceptanceApproval = Approval & { target: Extract<Approval['target'], { gate: 'acceptance' }> }
const TARGET: AcceptanceApproval['target'] = {
  gate: 'acceptance',
  spec_version_id: 'spec-v1',
  plan_digest: fakeDigest('d0'),
  commit_sha: CANDIDATE.commit,
  image_digest: CANDIDATE.image,
  ac_ids: ['AC-4'],
  validator_report_id: 'rp-validator',
  validator_report_digest: report('validator', 'pass').content_digest,
}
const approval = (state: Approval['state'], id = 'ap-acc', target = TARGET): AcceptanceApproval =>
  ({ id, state, target_digest: fakeDigest('d4'), target, ...(state === 'rejected' ? { feedback: '목록 정렬이 어색하다' } : {}) })

const withApprovals = (base: Snapshot, approvals: Approval[]): Snapshot => ({ ...base, approvals: [...base.approvals.filter((a) => a.target.gate !== 'acceptance'), ...approvals] })
const previewBase = previewScenario.snapshot

describe('합성 예시는 계약을 따른다', () => {
  test('사람 확인 승인이 있는 예시의 스냅샷과 승인이 스키마를 통과한다', () => {
    const withAcc = SCENARIOS.filter((s) => s.snapshot.approvals.some((a) => a.target.gate === 'acceptance'))
    expect(withAcc.map((s) => s.id).sort()).toEqual(['preview', 'release-approval', 'succeeded'])
    for (const s of withAcc) {
      expect(validSnapshot(s.snapshot)).toBe(true)
      for (const a of s.snapshot.approvals) expect(validApproval(a)).toBe(true)
    }
  })

  test('프리뷰 예시는 대기 승인 하나와 not_run으로 남은 사람 확인 AC를 가진다', () => {
    const pending = currentAcceptance(previewScenario.snapshot)
    expect(pending?.state).toBe('pending')
    const manual = pending!.target.ac_ids
    for (const id of manual) expect(previewScenario.acceptance.items.find((i) => i.id === id)?.status).toBe('not_run')
  })

  test('배포 예시의 배포 대상은 승인된 사람 확인 승인에 연결된다', () => {
    for (const s of [releaseScenario, doneScenario]) {
      const target = s.snapshot.approvals.find((a) => a.target.gate === 'release' && a.state !== 'invalidated')!.target as ReleaseTarget
      const linked = s.snapshot.approvals.find((a) => a.id === target.acceptance_approval_id)
      expect(linked?.state).toBe('approved')
    }
  })

  test('예시 소재는 중립이다(검증 과제 문구 없음)', () => {
    const text = JSON.stringify(previewScenario.snapshot)
    for (const word of ['카공', '카페', '카카오', '문의']) expect(text).not.toContain(word)
  })
})

describe('승인 선택', () => {
  test('대기 승인이 먼저, 없으면 마지막 결정, 무효는 제외한다', () => {
    const pending = approval('pending', 'ap-1')
    const rejected = approval('rejected', 'ap-0')
    const invalid = approval('invalidated', 'ap-old')
    expect(currentAcceptance(withApprovals(previewBase, [invalid, rejected, pending]))?.id).toBe('ap-1')
    expect(currentAcceptance(withApprovals(previewBase, [invalid, rejected]))?.id).toBe('ap-0')
    expect(currentAcceptance(withApprovals(previewBase, [invalid]))).toBeNull()
    expect(currentAcceptance(withApprovals(previewBase, []))).toBeNull()
    expect(acceptanceApprovals(withApprovals(previewBase, [invalid, pending])).map((a) => a.id)).toEqual(['ap-old', 'ap-1'])
  })
})

describe('현재 후보와 대상 비교', () => {
  const pair = reviewPair(previewBase)
  test('일치하면 사유가 없다', () => {
    expect(acceptanceMismatch(TARGET, pair)).toBeNull()
  })
  test.each([
    ['커밋', { commit_sha: 'f'.repeat(40) }],
    ['이미지', { image_digest: fakeDigest('ee') }],
    ['검증 보고서', { validator_report_id: 'rp-other' }],
    ['검증 보고서 해시', { validator_report_digest: fakeDigest('ff') }],
    ['명세', { spec_version_id: 'spec-v9' }],
  ])('%s가 다르면 사유를 돌려준다', (_name, patch) => {
    expect(acceptanceMismatch({ ...TARGET, ...patch }, pair)).toEqual(expect.stringContaining('다릅니다'))
  })
  test('검증 또는 보안 보고서가 없으면 후보를 확인할 수 없다', () => {
    const noSecurity = { ...pair, security: null }
    expect(acceptanceMismatch(TARGET, noSecurity)).toEqual(expect.stringContaining('보고서'))
    expect(acceptanceMismatch(TARGET, { validator: null, security: null })).not.toBeNull()
  })
})

describe('AC별 사람 확인 상태', () => {
  test('대기·승인·거절을 AC id별로 돌려준다', () => {
    for (const state of ['pending', 'approved', 'rejected'] as const) {
      const map = manualAcStates(withApprovals(previewBase, [approval(state)]))
      expect(map.get('AC-4')).toBe(state)
      expect(map.size).toBe(1)
    }
  })
  test('후보가 다른 승인과 무효 승인은 AC에 붙이지 않는다', () => {
    expect(manualAcStates(withApprovals(previewBase, [approval('approved', 'x', { ...TARGET, commit_sha: 'f'.repeat(40) })])).size).toBe(0)
    expect(manualAcStates(withApprovals(previewBase, [approval('invalidated')])).size).toBe(0)
    expect(manualAcStates(withApprovals(previewBase, [])).size).toBe(0)
  })
})

describe('AC 목록', () => {
  const props = (snapshot: Snapshot, acceptance = previewScenario.acceptance) => ({
    ids: ['AC-2', 'AC-4'],
    index: new Map(acceptance.items.map((i) => [i.id, i])),
    reports: snapshot.reports,
    manual: manualAcStates(snapshot),
  })

  test.each([
    ['pending', '사람 확인 대기'],
    ['approved', '사람 확인 승인됨'],
    ['rejected', '사람 확인 거절됨'],
  ] as const)('승인 상태 %s는 %s로 따로 보이고 판정은 미실행 그대로다', (state, text) => {
    const snapshot = withApprovals(previewBase, [approval(state)])
    const w = mount(AcceptanceList, { props: props(snapshot) })
    const row = w.findAll('li.ac').find((li) => li.text().includes('AC-4'))!
    expect(row.text()).toContain(text)
    expect(row.text()).toContain('미실행')
    expect(row.text()).not.toContain('충족')
    const other = w.findAll('li.ac').find((li) => li.text().includes('AC-2'))!
    expect(other.text()).not.toContain('사람 확인')
  })

  test('승인됨이어도 서버 판정이 met가 되기 전에는 충족으로 바꿔 표시하지 않는다', () => {
    const w = mount(AcceptanceList, { props: props(withApprovals(previewBase, [approval('approved')])) })
    expect(w.find('li.ac:nth-child(2)').text()).toContain('미실행')
  })

  test('승인 기록이 없는 옛 기록은 표시를 만들지 않는다', () => {
    const w = mount(AcceptanceList, { props: { ...props(withApprovals(previewBase, [])), manual: undefined } })
    expect(w.text()).not.toContain('사람 확인')
  })
})

describe('프리뷰의 사람 확인 구역', () => {
  const mountSection = (snapshot: Snapshot, send = vi.fn().mockResolvedValue(null), readOnly = false, source = exampleSource(previewScenario)) =>
    mount(AcceptanceApprovalSection, { attachTo: document.body, props: { snapshot, source, readOnly, send } })

  test('승인 대상 요약(후보 커밋·이미지·AC id·검증 보고서)을 보여 준다', async () => {
    const w = mountSection(withApprovals(previewBase, [approval('pending')]))
    await flushPromises()
    const text = w.text()
    expect(text).toContain('사람 확인 필요')
    expect(text).toContain(CANDIDATE.commit.slice(0, 12))
    expect(text).toContain('AC-4')
    expect(text).toContain('rp-validator')
    expect(text).toContain('사람 확인 대기')
    w.unmount()
  })

  test('승인은 decide 명령(approval_id, target_digest, approve)으로 보낸다', async () => {
    const send = vi.fn().mockResolvedValue(null)
    const w = mountSection(withApprovals(previewBase, [approval('pending')]), send)
    await flushPromises()
    await w.find('button.approve').trigger('click')
    await flushPromises()
    expect(send).toHaveBeenCalledTimes(1)
    expect(send.mock.calls[0][0]).toEqual({ action: 'decide', payload: { approval_id: 'ap-acc', target_digest: fakeDigest('d4'), decision: 'approve' } })
    w.unmount()
  })

  test('거절은 의견이 있어야 하고 의견은 원문 그대로 보낸다', async () => {
    const send = vi.fn().mockResolvedValue(null)
    const w = mountSection(withApprovals(previewBase, [approval('pending')]), send)
    await flushPromises()
    expect(w.find('button.reject').attributes('disabled')).toBeDefined()
    await w.find('textarea').setValue('  목록 정렬이 어색하다  ')
    expect(w.find('button.reject').attributes('disabled')).toBeUndefined()
    await w.find('button.reject').trigger('click')
    await flushPromises()
    expect(send.mock.calls[0][0]).toEqual({ action: 'decide', payload: { approval_id: 'ap-acc', target_digest: fakeDigest('d4'), decision: 'reject', feedback: '목록 정렬이 어색하다' } })
    w.unmount()
  })

  test('대상이 현재 후보와 다르면 승인을 막고 이유를 보여 준다', async () => {
    const stale = approval('pending', 'ap-acc', { ...TARGET, image_digest: fakeDigest('ee') })
    const send = vi.fn()
    const w = mountSection(withApprovals(previewBase, [stale]), send)
    await flushPromises()
    expect(w.find('[role="alert"]').text()).toContain('다릅니다')
    expect(w.find('button.approve').attributes('disabled')).toBeDefined()
    await w.find('button.approve').trigger('click')
    expect(send).not.toHaveBeenCalled()
    w.unmount()
  })

  test('이미 결정된 승인에는 버튼 대신 결정 결과와 의견을 보여 준다', async () => {
    const w = mountSection(withApprovals(previewBase, [approval('rejected')]))
    await flushPromises()
    expect(w.find('button.approve').exists()).toBe(false)
    expect(w.text()).toContain('사람 확인 거절됨')
    expect(w.text()).toContain('목록 정렬이 어색하다')
    w.unmount()
  })

  test('읽기 전용 재생에서는 보내지 않는다', async () => {
    const w = mountSection(withApprovals(previewBase, [approval('pending')]), vi.fn(), true)
    await flushPromises()
    expect(w.find('button.approve').exists()).toBe(false)
    expect(w.text()).toContain('읽기 전용')
    w.unmount()
  })

  test('무효화된 이전 승인은 건수만 알리고 쓰지 않는다', async () => {
    const w = mountSection(withApprovals(previewBase, [approval('invalidated', 'ap-old'), approval('pending')]))
    await flushPromises()
    expect(w.text()).toContain('무효화')
    expect(w.findAll('button.approve')).toHaveLength(1)
    w.unmount()
  })

  test('승인이 하나도 없으면 구역을 그리지 않는다(옛 기록)', async () => {
    const w = mountSection(withApprovals(previewBase, []))
    await flushPromises()
    expect(w.text()).toBe('')
    w.unmount()
  })

  test('검증 보고서 통과는 "사람 확인 제외 AC 충족"으로 안내하고 보고서의 manual_pending을 보여 준다', async () => {
    const source = { ...exampleSource(previewScenario), getArtifact: vi.fn().mockResolvedValue({ manual_pending: ['AC-4'] }) }
    const w = mountSection(withApprovals(previewBase, [approval('pending')]), vi.fn(), false, source)
    await flush()
    expect(w.text()).toContain('사람 확인을 제외한 AC')
    expect(w.text()).toContain('보고서가 사람 확인 대기로 표시한 AC')
    expect(source.getArtifact).toHaveBeenCalledWith('a-validation')
    w.unmount()
  })

  test('보고서 본문의 manual_pending이 승인 대상 AC와 다르면 알린다', async () => {
    const source = { ...exampleSource(previewScenario), getArtifact: vi.fn().mockResolvedValue({ manual_pending: ['AC-1', 'AC-4'] }) }
    const w = mountSection(withApprovals(previewBase, [approval('pending')]), vi.fn(), false, source)
    await flush()
    expect(w.text()).toContain('승인 대상 AC와 보고서가 표시한 AC가 다릅니다')
    w.unmount()
  })

  test('보고서 본문을 읽지 못해도 구역은 동작한다', async () => {
    const source = { ...exampleSource(previewScenario), getArtifact: vi.fn().mockRejectedValue(new Error('x')) }
    const w = mountSection(withApprovals(previewBase, [approval('pending')]), vi.fn(), false, source)
    await flush()
    expect(w.find('button.approve').exists()).toBe(true)
    expect(w.text()).not.toContain('보고서가 사람 확인 대기로 표시한 AC')
    w.unmount()
  })
})

describe('manual_pending 해석', () => {
  test('문자열 배열만 받고 그 밖은 null', () => {
    expect(manualPendingOf({ manual_pending: ['AC-1', 'AC-2'] })).toEqual(['AC-1', 'AC-2'])
    expect(manualPendingOf({ manual_pending: [] })).toEqual([])
    expect(manualPendingOf({ manual_pending: [1] })).toBeNull()
    expect(manualPendingOf({})).toBeNull()
    expect(manualPendingOf(null)).toBeNull()
    expect(manualPendingOf('x')).toBeNull()
  })
})

describe('프리뷰 대화상자와 알림', () => {
  test('프리뷰 대화상자에 사람 확인 구역이 있다', async () => {
    const send = vi.fn()
    const w = mount(PreviewDialog, {
      attachTo: document.body,
      props: { open: true, snapshot: previewScenario.snapshot, source: exampleSource(previewScenario), readOnly: false, selectedArtifactId: null, send },
    })
    await flush()
    expect(document.body.textContent).toContain('사람 확인 필요')
    w.unmount()
  })

  test('사람 확인 승인이 대기 중이면 프리뷰 알림이 그 결정을 안내한다', () => {
    const text = runAlerts(previewScenario.snapshot).find((a) => a.key === 'preview')!.text
    expect(text).toContain('사람 확인')
    const without = runAlerts(withApprovals(previewBase, [])).find((a) => a.key === 'preview')!.text
    expect(without).not.toContain('사람 확인')
  })
})

describe('배포 승인과의 결속', () => {
  const releaseTarget = (snapshot: Snapshot) => snapshot.approvals.find((a) => a.target.gate === 'release' && a.state === 'pending')!.target as ReleaseTarget
  // 기본은 승인에 연결되지 않은 배포 대상(옛 기록과 같은 모양). 연결은 patch로 준다
  const unlinked = (target: ReleaseTarget): ReleaseTarget => {
    const { acceptance_approval_id: _link, ...rest } = target
    return rest
  }
  const gate = (approvals: Approval[], patch: Partial<ReleaseTarget> = {}) => {
    const snapshot = withApprovals(releaseScenario.snapshot, approvals)
    return releaseAcceptanceGate(snapshot, { ...unlinked(releaseTarget(releaseScenario.snapshot)), ...patch })
  }

  test('연결된 승인이 승인됨이고 후보가 같으면 통과한다', () => {
    const result = gate([approval('approved', 'ap-acc')], { acceptance_approval_id: 'ap-acc' })
    expect(result.kind).toBe('ok')
  })
  test('연결된 승인이 대기·거절이면 막는다', () => {
    for (const state of ['pending', 'rejected'] as const) {
      const result = gate([approval(state, 'ap-acc')], { acceptance_approval_id: 'ap-acc' })
      expect(result).toMatchObject({ kind: 'blocked' })
    }
  })
  test('연결된 승인이 무효이거나 없으면 막는다', () => {
    expect(gate([approval('invalidated', 'ap-acc')], { acceptance_approval_id: 'ap-acc' }).kind).toBe('blocked')
    expect(gate([], { acceptance_approval_id: 'ap-missing' }).kind).toBe('blocked')
  })
  test('연결된 승인의 후보가 배포 대상과 다르면 막는다', () => {
    const other = approval('approved', 'ap-acc', { ...TARGET, commit_sha: 'f'.repeat(40) })
    expect(gate([other], { acceptance_approval_id: 'ap-acc' })).toMatchObject({ kind: 'blocked', reason: expect.stringContaining('다릅니다') })
  })
  test('연결 없이 대기·거절된 사람 확인 승인이 있으면 막는다', () => {
    expect(gate([approval('pending')]).kind).toBe('blocked')
    expect(gate([approval('rejected')]).kind).toBe('blocked')
  })
  test('승인됐는데 배포 대상이 연결되지 않았으면 막는다', () => {
    expect(gate([approval('approved')])).toMatchObject({ kind: 'blocked', reason: expect.stringContaining('연결') })
  })
  test('사람 확인 승인이 전혀 없으면(옛 기록) 표시하지 않는다', () => {
    expect(gate([]).kind).toBe('none')
  })

  const mountRelease = (snapshot: Snapshot, releaseEnabled: boolean) =>
    mount(ReleaseApprovalDialog, {
      attachTo: document.body,
      props: {
        open: true,
        approval: snapshot.approvals.find((a) => a.target.gate === 'release' && a.state === 'pending') as never,
        snapshot,
        source: exampleSource(releaseScenario),
        readOnly: false,
        releaseEnabled,
        send: vi.fn(),
      },
    })

  test('배포 승인 화면이 연결된 사람 확인 승인을 보여 준다', async () => {
    const w = mountRelease(releaseScenario.snapshot, true)
    await flushPromises()
    expect(document.body.textContent).toContain('사람 확인 승인')
    expect(document.body.textContent).toContain('승인됨')
    expect(document.body.textContent).toContain('ap-acceptance-1')
    const approve = [...document.querySelectorAll('button')].find((b) => b.textContent?.includes('배포 승인'))
    expect(approve?.hasAttribute('disabled')).toBe(false)
    w.unmount()
  })

  test('사람 확인 승인이 대기 중이면 배포 승인을 비활성화하고 사유를 안내한다', async () => {
    const snapshot = withApprovals(releaseScenario.snapshot, [approval('pending', 'ap-acceptance-1')])
    const w = mountRelease(snapshot, true)
    await flushPromises()
    expect(document.body.textContent).toContain('사람 확인 승인이 아직 승인되지 않았습니다')
    const approve = [...document.querySelectorAll('button')].find((b) => b.textContent?.includes('배포 승인'))
    expect(approve?.hasAttribute('disabled')).toBe(true)
    w.unmount()
  })

  test('옛 기록(사람 확인 승인 없음)에는 이 구역을 그리지 않는다', async () => {
    const old = withApprovals(releaseScenario.snapshot, [])
    const snapshot = { ...old, approvals: old.approvals.map((a) => (a.target.gate === 'release' ? { ...a, target: unlinked(a.target as ReleaseTarget) } : a)) }
    const w = mountRelease(snapshot, true)
    await flushPromises()
    expect(document.body.textContent).not.toContain('사람 확인 승인')
    w.unmount()
  })
})

describe('작업 화면 연결', () => {
  test('프리뷰 예시의 AC 목록에 사람 확인 대기가 보이고 충족으로 세지 않는다', async () => {
    const w = mount(RunWorkspace, { attachTo: document.body, props: { source: exampleSource(previewScenario) } })
    await flush()
    expect(w.text()).toContain('사람 확인 대기')
    w.unmount()
  })
})
