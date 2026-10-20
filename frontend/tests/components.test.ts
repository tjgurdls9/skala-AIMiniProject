import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeAll, describe, expect, test, vi } from 'vitest'
import { ApiError } from '../src/api/errors'
import ChangeRequestForm from '../src/components/ChangeRequestForm.vue'
import PlanApprovalDialog from '../src/components/PlanApprovalDialog.vue'
import PreviewFrame from '../src/components/PreviewFrame.vue'
import ReleaseApprovalDialog from '../src/components/ReleaseApprovalDialog.vue'
import SourceBadge from '../src/components/SourceBadge.vue'
import { useCommandForm } from '../src/composables/useCommandForm'
import { pendingApproval } from '../src/model/derive'
import { exampleSource } from '../src/examples/exampleSource'
import { findScenario } from '../src/examples/scenarios'
import { fakeDigest } from '../src/examples/base'

beforeAll(() => {
  // happy-dom에 없는 모달 API는 열림 상태만 흉내 낸다
  const proto = HTMLDialogElement.prototype as HTMLDialogElement & { showModal(): void }
  if (!proto.showModal) proto.showModal = function (this: HTMLDialogElement) { this.setAttribute('open', '') }
})
afterEach(() => sessionStorage.clear())

const scenario = (id: string) => findScenario(id)!
const button = (w: ReturnType<typeof mount>, text: string) => w.findAll('button').find((b) => b.text().includes(text))!

describe('출처 배지', () => {
  test('합성 예시는 snapshot.mode가 live여도 LIVE로 표시하지 않는다', () => {
    const w = mount(SourceBadge, { props: { kind: 'example', snapshot: scenario('building').snapshot } })
    expect(w.text()).toContain('합성 예시 · 실제 실행 아님')
    expect(w.text()).not.toContain('LIVE')
  })
  test('실제 API의 replay는 원본 실행·기록 시각·manifest를 함께 표시한다', () => {
    const snapshot = {
      ...scenario('building').snapshot,
      mode: 'replay' as const,
      replay_source: { source_run_id: 'run-7', recorded_at: '2026-10-20T01:00:00Z', manifest_digest: fakeDigest('9a') },
    }
    const w = mount(SourceBadge, { props: { kind: 'live', snapshot } })
    expect(w.text()).toContain('실제 기록 재생 · 읽기 전용')
    expect(w.text()).toContain('run-7')
    expect(mount(SourceBadge, { props: { kind: 'live', snapshot: scenario('building').snapshot } }).text()).toContain('LIVE')
    expect(mount(SourceBadge, { props: { kind: 'live', snapshot: null } }).text()).toContain('연결 확인 중')
  })
})

describe('기획 승인', () => {
  const s = scenario('plan-approval')
  const mountDialog = (send: (...args: unknown[]) => Promise<ApiError | null> = vi.fn(async () => null)) =>
    mount(PlanApprovalDialog, {
      attachTo: document.body,
      props: { open: true, approval: pendingApproval(s.snapshot, 'plan'), specArtifactId: 'a-spec', source: exampleSource(s), runId: 'r1', readOnly: false, send },
    })

  test('서버가 준 approval_id·target_digest를 그대로 보낸다', async () => {
    const send = vi.fn(async (): Promise<ApiError | null> => null)
    const w = mountDialog(send)
    await flushPromises()
    expect(w.text()).toContain('합성 고객 문의 CSV')
    await button(w, '이 기획으로 구현 시작').trigger('click')
    await flushPromises()
    expect(send).toHaveBeenCalledOnce()
    const [input] = send.mock.calls[0] as unknown as [{ action: string; payload: Record<string, unknown> }]
    expect(input).toEqual({ action: 'decide', payload: { approval_id: 'ap-plan-1', target_digest: fakeDigest('d1'), decision: 'approve' } })
    expect(w.emitted('close')).toHaveLength(1)
    w.unmount()
  })

  test('거절은 의견이 있어야 하고, 409면 의견을 보존한 채 원인과 다음 행동을 보여준다', async () => {
    const send = vi.fn(async (): Promise<ApiError | null> => new ApiError(409, 'STALE_APPROVAL', '승인 대상이 바뀌었습니다'))
    const w = mountDialog(send)
    await flushPromises()
    expect(button(w, '수정 요청(거절)').attributes('disabled')).toBeDefined()
    await w.find('textarea').setValue('비범위에 메일 연동을 다시 넣어 주세요')
    await button(w, '수정 요청(거절)').trigger('click')
    await flushPromises()
    expect(w.text()).toContain('승인 대상이 바뀌었습니다')
    expect(w.text()).toContain('최신 상태를 다시 불러왔으니')
    expect((w.find('textarea').element as HTMLTextAreaElement).value).toBe('비범위에 메일 연동을 다시 넣어 주세요')
    expect(sessionStorage.getItem('draft:r1:plan-feedback')).toBe('비범위에 메일 연동을 다시 넣어 주세요')
    expect(w.emitted('close')).toBeUndefined()
    w.unmount()
  })

  test('대기 중 승인이 없으면 결정 버튼이 없다', async () => {
    const w = mount(PlanApprovalDialog, {
      attachTo: document.body,
      props: { open: true, approval: null, specArtifactId: null, source: exampleSource(s), runId: 'r1', readOnly: false, send: vi.fn() },
    })
    await flushPromises()
    expect(w.text()).toContain('대기 중인 기획 승인이 없습니다')
    expect(w.findAll('button').map((b) => b.text())).toEqual(['닫기'])
    w.unmount()
  })
})

describe('배포 승인', () => {
  test('두 검토가 통과하고 대상과 같은 후보일 때만 승인 버튼이 열린다', async () => {
    const s = scenario('release-approval')
    const send = vi.fn(async () => null)
    const w = mount(ReleaseApprovalDialog, {
      attachTo: document.body,
      props: { open: true, approval: pendingApproval(s.snapshot, 'release'), snapshot: s.snapshot, source: exampleSource(s), readOnly: false, send },
    })
    await flushPromises()
    expect(w.text()).toContain('스테이징 (합성)')
    expect(w.text()).toContain('이전 배포 대상 1건은 무효화')
    const approve = button(w, '배포 승인')
    expect(approve.attributes('disabled')).toBeUndefined()
    await approve.trigger('click')
    await flushPromises()
    expect((send.mock.calls[0] as unknown[])[0]).toMatchObject({ action: 'decide', payload: { approval_id: 'ap-release-2', target_digest: fakeDigest('d3'), decision: 'approve' } })
    w.unmount()

    const failing = { ...s.snapshot, reports: s.snapshot.reports.map((r) => (r.role === 'security' ? { ...r, verdict: 'fail' as const } : r)) }
    const blocked = mount(ReleaseApprovalDialog, {
      attachTo: document.body,
      props: { open: true, approval: pendingApproval(failing, 'release'), snapshot: failing, source: exampleSource(s), readOnly: false, send },
    })
    await flushPromises()
    expect(blocked.text()).toContain('두 검토가 모두 통과하지 않아')
    expect(button(blocked, '배포 승인').attributes('disabled')).toBeDefined()
    blocked.unmount()
  })

  test('환경 정보가 없으면 미설정으로 표시한다', async () => {
    const s = scenario('release-approval')
    const w = mount(ReleaseApprovalDialog, {
      attachTo: document.body,
      props: { open: true, approval: pendingApproval(s.snapshot, 'release'), snapshot: s.snapshot, source: exampleSource({ ...s, environments: {} }), readOnly: false, send: vi.fn() },
    })
    await flushPromises()
    expect(w.text()).toContain('제공하지 않습니다(미설정)')
    w.unmount()
  })
})

describe('수정 요청', () => {
  test('범위와 근거 아티팩트를 함께 보내고 성공하면 초안을 비운다', async () => {
    const send = vi.fn(async () => null)
    const w = mount(ChangeRequestForm, { props: { runId: 'r2', artifactIds: ['a-preview'], artifactTitles: { 'a-preview': '프리뷰' }, disabled: false, send } })
    await w.find('input[value="spec"]').setValue()
    await w.find('textarea').setValue('검색에 날짜 필터 추가')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect((send.mock.calls[0] as unknown[])[0]).toEqual({ action: 'request_changes', payload: { scope: 'spec', feedback: '검색에 날짜 필터 추가', artifact_ids: ['a-preview'] } })
    expect(w.emitted('sent')).toHaveLength(1)
    expect(sessionStorage.getItem('draft:r2:change-feedback')).toBeNull()
  })

  test('저장된 초안을 다시 열면 복원한다', () => {
    sessionStorage.setItem('draft:r3:change-feedback', '이전 입력')
    const w = mount(ChangeRequestForm, { props: { runId: 'r3', artifactIds: [], artifactTitles: {}, disabled: false, send: vi.fn() } })
    expect((w.find('textarea').element as HTMLTextAreaElement).value).toBe('이전 입력')
  })
})

describe('명령 ID', () => {
  test('네트워크 실패 재시도는 같은 ID, 대상 충돌 뒤에는 새 ID, 보내는 중 중복 호출은 무시', async () => {
    const form = useCommandForm()
    const ids: string[] = []
    await form.run(async (id) => (ids.push(id), new ApiError(0, 'NETWORK', 'x')))
    await form.run(async (id) => (ids.push(id), new ApiError(409, 'VERSION_CONFLICT', 'x')))
    await form.run(async (id) => (ids.push(id), null))
    expect(ids[0]).toBe(ids[1])
    expect(ids[2]).not.toBe(ids[1])
    let release: () => void = () => {}
    const slow = form.run((id) => new Promise((r) => { ids.push(id); release = () => r(null) }))
    expect(await form.run(async () => null)).toBe(false)
    release()
    expect(await slow).toBe(true)
  })
})

describe('프리뷰 격리', () => {
  const at = (preview: unknown) => mount(PreviewFrame, { props: { preview } }).text()
  test('주소가 없거나 origin이 다르거나 같은 hostname이면 열지 않는다', () => {
    expect(at(null)).toContain('프리뷰 주소가 제공되지 않았습니다')
    expect(at({ url: 'https://a.example/x', origin: 'https://b.example', commit_sha: 'c' })).toContain('선언된 origin과 다릅니다')
    expect(at({ url: 'javascript:alert(1)', origin: 'javascript:', commit_sha: 'c' })).toMatch(/형식|origin/)
    expect(at({ url: `http://${location.hostname}:9999/`, origin: `http://${location.hostname}:9999`, commit_sha: 'c' })).toContain('같은 hostname')
  })
  test('별도 origin이면 allow-same-origin 없는 sandbox iframe으로 연다', () => {
    const w = mount(PreviewFrame, { props: { preview: { url: 'https://preview.example/app', origin: 'https://preview.example', commit_sha: 'cd'.repeat(20) } } })
    const frame = w.find('iframe')
    expect(frame.attributes('sandbox')).toBe('allow-scripts allow-forms')
    expect(frame.attributes('referrerpolicy')).toBe('no-referrer')
  })
})
