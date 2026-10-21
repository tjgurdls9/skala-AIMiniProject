// CR-C16·CR-C17(계약 76147c6): 일반 시작 프로젝트 ID, 아이디어 대안·작업 분해·점검 명세·의존성. 모두 선택 필드다.
import Ajv2020 from 'ajv/dist/2020'
import addFormats from 'ajv-formats'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeAll, describe, expect, test, vi } from 'vitest'
import type { PlanView } from '../src/api/types'
import PlanApprovalDialog from '../src/components/PlanApprovalDialog.vue'
import PlanViewBody from '../src/components/PlanViewBody.vue'
import { PLAN_VIEW } from '../src/examples/base'
import { exampleSource } from '../src/examples/exampleSource'
import { findScenario } from '../src/examples/scenarios'
import { pendingApproval } from '../src/model/derive'
import { acCoverage, isPlanExtras } from '../src/model/planExtras'
import { isPlanSupport } from '../src/model/planSupport'
import { isPlanView } from '../src/model/planView'

beforeAll(() => {
  const proto = HTMLDialogElement.prototype as HTMLDialogElement & { showModal(): void }
  if (!proto.showModal) proto.showModal = function (this: HTMLDialogElement) { this.setAttribute('open', '') }
  if (!('ResizeObserver' in globalThis)) {
    ;(globalThis as Record<string, unknown>).ResizeObserver = class { observe() {} disconnect() {} }
  }
})
afterEach(() => {
  document.body.innerHTML = ''
  sessionStorage.clear()
})

const dir = resolve(__dirname, '../../docs/planning')
const ajv = new Ajv2020({ strict: false, allErrors: true })
addFormats(ajv)
ajv.addSchema(JSON.parse(readFileSync(resolve(dir, 'protocol.v1.schema.json'), 'utf8')), 'protocol.v1.schema.json')
ajv.addSchema(JSON.parse(readFileSync(resolve(dir, 'http.v1.schema.json'), 'utf8')), 'http.v1.schema.json')
const validPlan = (v: unknown) => ajv.getSchema('http.v1.schema.json#/$defs/PlanView')!(v)
const validChange = (v: unknown) => ajv.getSchema('protocol.v1.schema.json#/$defs/ChangePayload')!(v)

const plain = (): PlanView => {
  const copy = { ...PLAN_VIEW } as Partial<PlanView>
  for (const k of ['alternatives', 'selected_alternative_id', 'single_alternative_reason', 'work_plan', 'omitted_areas', 'verification', 'manual_acceptance', 'dependencies', 'tool_policy_digest'] as const) delete copy[k]
  return copy as PlanView
}
const withExtras = (extra: Partial<PlanView>): PlanView => ({ ...plain(), ...extra })
/** 대안은 1–3개 튜플 타입이라 테스트에서는 배열로 다룬다 */
type Alt = { id: string; summary: string; differences: string; risks: string }
const ALTS = PLAN_VIEW.alternatives as unknown as Alt[]

describe('CR-C16 일반 시작 프로젝트 ID', () => {
  const base = PLAN_VIEW.support!
  test('패턴을 만족하는 서버 ID는 이름과 상관없이 받는다(옛 기록의 ID 포함)', () => {
    for (const template_id of ['starter-app-v1', 'requests-v1', 'cafemap-v1', 'a', '0x-1']) {
      expect(validPlan({ ...PLAN_VIEW, support: { ...base, template_id } })).toBe(true)
      expect(isPlanSupport({ ...base, template_id })).toBe(true)
    }
  })
  test('패턴 밖 ID는 형식 오류다', () => {
    for (const template_id of ['', 'Starter', '-lead', 'has space', 'under_score', 'a'.repeat(64)]) {
      expect(validPlan({ ...PLAN_VIEW, support: { ...base, template_id } })).toBe(false)
      expect(isPlanSupport({ ...base, template_id })).toBe(false)
    }
  })
})

describe('CR-C17 PlanView 확장 필드 계약', () => {
  test('합성 기획(대안·작업 분해·점검·의존성 포함)이 스키마와 가드를 통과한다', () => {
    expect(ALTS.length).toBeGreaterThanOrEqual(2)
    expect(PLAN_VIEW.work_plan?.length).toBeGreaterThan(0)
    expect(PLAN_VIEW.verification?.length).toBeGreaterThan(0)
    expect(validPlan(PLAN_VIEW)).toBe(true)
    expect(isPlanView(PLAN_VIEW)).toBe(true)
    expect(isPlanExtras(PLAN_VIEW)).toBe(true)
  })

  test('새 필드가 없는 옛 기록도 그대로 통과한다', () => {
    expect(validPlan(plain())).toBe(true)
    expect(isPlanView(plain())).toBe(true)
  })

  test('계약 밖 본문은 스키마와 가드 모두 거절한다(기획 본문 전체를 형식 오류로 본다)', () => {
    const alt = ALTS[0]
    const item = PLAN_VIEW.work_plan![0]
    const http = PLAN_VIEW.verification!.find((c) => c.kind === 'http')!
    const bad: Array<[string, Partial<PlanView>]> = [
      ['대안 0개', { alternatives: [] as never }],
      ['대안 4개', { alternatives: [alt, { ...alt, id: 'b' }, { ...alt, id: 'c' }, { ...alt, id: 'd' }] as never }],
      ['대안 id 패턴', { alternatives: [{ ...alt, id: 'a b' }] as never }],
      ['대안 위험 비어 있음', { alternatives: [{ ...alt, risks: '' }] as never }],
      ['대안에 모르는 키', { alternatives: [{ ...alt, extra: 1 }] as never }],
      ['작업 종류 밖', { work_plan: [{ ...item, kind: 'design' as never }] }],
      ['작업 쓰기 범위 비어 있음', { work_plan: [{ ...item, write_scope: [] as never }] }],
      ['점검 종류 밖', { verification: [{ ...http, kind: 'sql' } as never] }],
      ['점검이 AC에 연결되지 않음', { verification: [{ ...http, ac_ids: [] } as never] }],
      ['사람 확인 사유 없음', { manual_acceptance: [{ ac_id: 'AC-1' } as never] }],
      ['의존성 문자열 아님', { dependencies: { pip: [1] } as never }],
      ['도구 정책 digest 형식', { tool_policy_digest: 'nope' }],
      ['생략 영역 종류 밖', { omitted_areas: [{ kind: 'release', reason: 'x' } as never] }],
    ]
    for (const [name, extra] of bad) {
      const plan = withExtras(extra)
      expect(validPlan(plan), name).toBe(false)
      expect(isPlanView(plan), name).toBe(false)
    }
  })

  test('선택한 대안 id가 대안 목록에 없으면 기획 본문 전체를 형식 오류로 본다', () => {
    expect(isPlanView(withExtras({ alternatives: PLAN_VIEW.alternatives, selected_alternative_id: 'nope' }))).toBe(false)
  })

  test('request_changes의 alternative_id가 계약(ChangePayload)에 있다', () => {
    expect(validChange({ scope: 'spec', feedback: '다른 대안으로', alternative_id: 'alt-b' })).toBe(true)
    expect(validChange({ scope: 'spec', feedback: '다른 대안으로', alternative_id: 'a b' })).toBe(false)
  })
})

describe('AC별 점검 연결', () => {
  const ac = (id: string) => ({ id, title: `AC ${id}`, description: '설명' })
  const plan = withExtras({
    acceptance: [ac('AC-1'), ac('AC-2'), ac('AC-3')],
    verification: [{ id: 'c1', ac_ids: ['AC-1', 'AC-2'], kind: 'file', path: 'README.md', expect: { exists: true } }],
    manual_acceptance: [{ ac_id: 'AC-2', reason: '사람이 본다' }],
  })

  test('점검·사람 확인이 연결된 AC와 둘 다 없는 AC를 가른다', () => {
    const r = acCoverage(plan)
    expect(r.kind).toBe('known')
    if (r.kind !== 'known') return
    expect(r.rows.map((x) => [x.ac.id, x.checks.length, x.manual?.reason ?? null, x.uncovered])).toEqual([
      ['AC-1', 1, null, false],
      ['AC-2', 1, '사람이 본다', false],
      ['AC-3', 0, null, true],
    ])
    expect(r.uncoveredCount).toBe(1)
  })

  test('점검 정보가 둘 다 없는 옛 기록은 미제공으로 보고, 지원되는 것으로 추정하지 않는다', () => {
    expect(acCoverage(plain()).kind).toBe('missing')
  })

  test('한쪽만 있어도 정보가 제공된 것이다(없는 쪽은 빈 목록)', () => {
    const r = acCoverage(withExtras({ acceptance: [ac('AC-1')], manual_acceptance: [{ ac_id: 'AC-1', reason: 'x' }] }))
    expect(r.kind).toBe('known')
  })
})

describe('기획 본문 표시(PlanViewBody)', () => {
  const region = (w: ReturnType<typeof mount>, label: string) => w.find(`section[aria-label="${label}"]`)

  test('아이디어 대안의 요약·차이·위험을 보여 주고 선택된 대안을 표시한다', () => {
    const w = mount(PlanViewBody, { props: { plan: PLAN_VIEW } })
    const r = region(w, '아이디어 대안')
    const [a, b] = ALTS
    expect(r.text()).toContain(a.summary)
    expect(r.text()).toContain(a.differences)
    expect(r.text()).toContain(a.risks)
    expect(r.text()).toContain(b.summary)
    expect(r.findAll('[aria-current="true"]')).toHaveLength(1)
    expect(r.find('[aria-current="true"]').text()).toContain(a.summary)
    expect(r.find('[aria-current="true"]').text()).toContain('선택됨')
    expect(r.findAll('button')).toHaveLength(0) // 읽기 전용에는 버튼이 없다
  })

  test('대안이 하나면 그 이유를 보여 준다', () => {
    const w = mount(PlanViewBody, { props: { plan: withExtras({ alternatives: [ALTS[0]], selected_alternative_id: ALTS[0].id, single_alternative_reason: '요청이 한 가지 방식으로만 해석된다' }) } })
    expect(region(w, '아이디어 대안').text()).toContain('대안이 하나뿐인 이유')
    expect(region(w, '아이디어 대안').text()).toContain('요청이 한 가지 방식으로만 해석된다')
  })

  test('작업 분해는 종류·의존성·AC 연결·쓰기 범위를 보여 주고, 생략된 영역과 이유를 밝힌다', () => {
    const plan = withExtras({
      acceptance: PLAN_VIEW.acceptance,
      work_plan: [
        { id: 'w1', kind: 'contract', title: 'API 계약', depends_on: [], acceptance_ids: ['AC-2'], write_scope: ['docs/api.md'] },
        { id: 'w2', kind: 'backend', title: '조회 API', depends_on: ['w1'], acceptance_ids: ['AC-3', 'AC-2'], write_scope: ['app/**', 'tests/api/**'] },
      ],
      omitted_areas: [{ kind: 'ai_data', reason: '모델이 필요하지 않아 생략' }],
    })
    const r = region(mount(PlanViewBody, { props: { plan } }), '작업 분해')
    const text = r.text()
    expect(text).toContain('API 계약')
    expect(text).toContain('계약')
    expect(text).toContain('백엔드')
    expect(text).toContain('의존: w1')
    expect(text).toContain('AC-3')
    expect(text).toContain('app/**')
    expect(text).toContain('tests/api/**')
    expect(text).toContain('생략한 영역')
    expect(text).toContain('AI·데이터')
    expect(text).toContain('모델이 필요하지 않아 생략')
  })

  test('AC마다 연결된 점검 또는 사람 확인을 보여 주고, 둘 다 없는 AC는 눈에 띄게 표시한다', () => {
    const plan = withExtras({
      acceptance: [{ id: 'AC-1', title: '분류', description: 'd' }, { id: 'AC-2', title: '화면', description: 'd' }, { id: 'AC-3', title: '배포', description: 'd' }],
      verification: [
        { id: 'c-cmd', ac_ids: ['AC-1'], kind: 'command', argv: ['pytest', '-q'], expect: { exit: 0, stdout_contains: ['passed'] } },
        { id: 'c-http', ac_ids: ['AC-1'], kind: 'http', steps: [{ method: 'GET', path: '/items', expect: { status: 200 } }] },
        { id: 'c-file', ac_ids: ['AC-1'], kind: 'file', path: 'Dockerfile', expect: { exists: true, contains: ['FROM'] } },
      ],
      manual_acceptance: [{ ac_id: 'AC-2', reason: '화면은 사람이 확인한다' }],
    })
    const r = region(mount(PlanViewBody, { props: { plan } }), 'AC별 점검')
    const text = r.text()
    expect(text).toContain('pytest -q')
    expect(text).toContain('종료 코드 0')
    expect(text).toContain('GET /items')
    expect(text).toContain('상태 200')
    expect(text).toContain('Dockerfile')
    expect(text).toContain('사람 확인')
    expect(text).toContain('화면은 사람이 확인한다')
    const rows = r.findAll('li.ac-row')
    expect(rows).toHaveLength(3)
    expect(rows[2].classes()).toContain('uncovered')
    expect(rows[2].text()).toContain('연결된 점검도 사람 확인도 없음')
    expect(rows[0].classes()).not.toContain('uncovered')
    expect(r.text()).toContain('1개 AC')
  })

  test('의존성 범위와 도구 정책 digest를 보여 준다', () => {
    const w = mount(PlanViewBody, { props: { plan: PLAN_VIEW } })
    const r = region(w, '의존성·도구 정책')
    expect(r.text()).toContain('pip')
    expect(r.text()).toContain(PLAN_VIEW.dependencies!.pip![0] as string)
    expect(r.text()).toContain('npm')
    expect(r.text()).toContain('범위 밖 설치는 자동 허용되지 않고')
    expect(r.text()).toContain('도구 정책')
  })

  test('새 필드가 없는 옛 기록은 각 구역을 미제공·미확인으로 표시하고 지원·검증이 있다고 추정하지 않는다', () => {
    const w = mount(PlanViewBody, { props: { plan: plain() } })
    for (const label of ['아이디어 대안', '작업 분해', 'AC별 점검', '의존성·도구 정책']) {
      expect(region(w, label).text(), label).toContain('미제공 · 미확인')
    }
    expect(w.text()).not.toContain('연결된 점검도 사람 확인도 없음')
  })
})

describe('기획 승인 화면: 다른 대안 선택', () => {
  const scenario = findScenario('plan-approval')!
  function dialog(plan: PlanView, send = vi.fn(async () => null), readOnly = false) {
    const source = { ...exampleSource(scenario), getArtifact: async () => plan }
    const w = mount(PlanApprovalDialog, {
      attachTo: document.body,
      props: { open: true, approval: pendingApproval(scenario.snapshot, 'plan'), specArtifactId: 'a-spec', source, runId: 'r1', readOnly, send },
    })
    return { w, send }
  }
  const btn = (w: ReturnType<typeof mount>, text: string) => w.findAll('button').find((b) => b.text().includes(text))

  test('선택되지 않은 대안에만 "이 대안으로 다시 기획"이 있고, 눌러도 바로 보내지 않고 확인을 거친다', async () => {
    const { w, send } = dialog(PLAN_VIEW)
    await flushPromises()
    const choose = w.findAll('button.choose-alt')
    expect(choose).toHaveLength(ALTS.length - 1)
    await choose[0].trigger('click')
    expect(send).not.toHaveBeenCalled()
    expect(w.text()).toContain('현재 기획은 취소되고')
    expect(w.text()).toContain('새 승인이 필요합니다')
    w.unmount()
  })

  test('확인하면 request_changes(scope=spec, alternative_id)를 보내고, 승인(decide)은 보내지 않는다', async () => {
    const { w, send } = dialog(PLAN_VIEW)
    await flushPromises()
    await w.find('button.choose-alt').trigger('click')
    await btn(w, '이 대안으로 보내기')!.trigger('click')
    await flushPromises()
    expect(send).toHaveBeenCalledOnce()
    const [input] = send.mock.calls[0] as unknown as [{ action: string; payload: Record<string, unknown> }, string]
    expect(input.action).toBe('request_changes')
    expect(input.payload.scope).toBe('spec')
    expect(input.payload.alternative_id).toBe(ALTS[1].id)
    expect(String(input.payload.feedback).length).toBeGreaterThan(0)
    expect(validChange(input.payload)).toBe(true)
    w.unmount()
  })

  test('의견을 적었다면 그 의견을 함께 보낸다', async () => {
    const { w, send } = dialog(PLAN_VIEW)
    await flushPromises()
    await w.find('textarea').setValue('서버 없는 쪽이 낫겠습니다')
    await w.find('button.choose-alt').trigger('click')
    await btn(w, '이 대안으로 보내기')!.trigger('click')
    await flushPromises()
    const [input] = send.mock.calls[0] as unknown as [{ payload: Record<string, unknown> }, string]
    expect(String(input.payload.feedback)).toContain('서버 없는 쪽이 낫겠습니다')
    w.unmount()
  })

  test('확인 단계에서 취소하면 아무것도 보내지 않는다', async () => {
    const { w, send } = dialog(PLAN_VIEW)
    await flushPromises()
    await w.find('button.choose-alt').trigger('click')
    await btn(w, '취소')!.trigger('click')
    expect(send).not.toHaveBeenCalled()
    expect(w.text()).not.toContain('현재 기획은 취소되고')
    w.unmount()
  })

  test('읽기 전용(재생)에는 대안 선택 버튼이 없다', async () => {
    const { w } = dialog(PLAN_VIEW, vi.fn(), true)
    await flushPromises()
    expect(w.findAll('button.choose-alt')).toHaveLength(0)
    w.unmount()
  })

  test('승인 가능 여부는 서버 판정(implementation_allowed)만 따른다: 점검 없는 AC가 있어도 클라이언트가 막지 않는다', async () => {
    const plan = withExtras({
      acceptance: [{ id: 'AC-1', title: 't', description: 'd' }],
      verification: [],
      manual_acceptance: [],
      support: { ...PLAN_VIEW.support!, implementation_allowed: true },
    })
    const { w } = dialog(plan)
    await flushPromises()
    expect(w.findAll('li.ac-row.uncovered')).toHaveLength(1)
    expect(btn(w, '이 기획으로 구현 시작')!.attributes('disabled')).toBeUndefined()
    w.unmount()
    const blocked = dialog({ ...plan, support: { ...PLAN_VIEW.support!, implementation_allowed: false } })
    await flushPromises()
    expect(btn(blocked.w, '이 기획으로 구현 시작')!.attributes('disabled')).toBeDefined()
    blocked.w.unmount()
  })

  test('승인 화면에는 대안·작업 분해·점검 구역이 한 번씩만 나온다', async () => {
    const { w } = dialog(PLAN_VIEW)
    await flushPromises()
    for (const label of ['아이디어 대안', '작업 분해', 'AC별 점검', '의존성·도구 정책']) {
      expect(w.findAll(`section[aria-label="${label}"]`), label).toHaveLength(1)
    }
    w.unmount()
  })
})
