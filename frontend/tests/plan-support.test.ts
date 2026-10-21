// CR-C14 기획별 지원 공백(PlanView.support). 계약: Codex a6eb8a4. Runtime 템플릿 상태로 대신하지 않는다.
import Ajv2020 from 'ajv/dist/2020'
import addFormats from 'ajv-formats'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeAll, describe, expect, test, vi } from 'vitest'
import type { PlanView } from '../src/api/types'
import PlanApprovalDialog from '../src/components/PlanApprovalDialog.vue'
import { fakeDigest, PLAN_VIEW } from '../src/examples/base'
import { exampleSource } from '../src/examples/exampleSource'
import { findScenario } from '../src/examples/scenarios'
import { pendingApproval } from '../src/model/derive'
import { isPlanSupport } from '../src/model/planSupport'
import { isPlanView } from '../src/model/planView'

beforeAll(() => {
  const proto = HTMLDialogElement.prototype as HTMLDialogElement & { showModal(): void }
  if (!proto.showModal) proto.showModal = function (this: HTMLDialogElement) { this.setAttribute('open', '') }
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

type Support = NonNullable<PlanView['support']>
const CAFEMAP: Support = {
  template_id: 'cafemap-v1',
  spec_version_id: PLAN_VIEW.spec_version_id,
  request_digest: fakeDigest('9a'),
  implementation_allowed: false,
  unsupported: [{ request_quote: '내 위치를 기반으로 주변 카페를 추천', reason: '장소 데이터 공급자가 정해지지 않았습니다.', requires: ['장소 데이터 공급자', '위치 동의 경로'] }],
  external: [{ provider: null, purpose: '지도·장소 검색', needs: ['free_eligibility', 'key', 'attribution', 'consent'], status: 'deferred', reason: '사용자 선택: 외부 연결은 나중에 결정' }],
}

const scenario = findScenario('plan-approval')!
function dialog(plan: unknown, send = vi.fn(async () => null)) {
  const source = { ...exampleSource(scenario), getArtifact: async () => plan }
  const w = mount(PlanApprovalDialog, {
    attachTo: document.body,
    props: { open: true, approval: pendingApproval(scenario.snapshot, 'plan'), specArtifactId: 'a-spec', source, runId: 'r1', readOnly: false, send },
  })
  return { w, send }
}
const button = (w: ReturnType<typeof mount>, text: string) => w.findAll('button').find((b) => b.text().includes(text))!

describe('PlanView.support 계약', () => {
  test('합성 예시와 카공지도 공백 본문이 스키마와 가드를 통과한다', () => {
    expect(validPlan(PLAN_VIEW)).toBe(true)
    expect(isPlanView(PLAN_VIEW)).toBe(true)
    const withGap = { ...PLAN_VIEW, support: CAFEMAP }
    expect(validPlan(withGap)).toBe(true)
    expect(isPlanView(withGap)).toBe(true)
  })

  test('support가 계약 밖이면 기획 본문 전체를 형식 오류로 본다', () => {
    const bad = [
      { ...CAFEMAP, template_id: 'mapapp-v9' },
      { ...CAFEMAP, implementation_allowed: 'no' },
      { ...CAFEMAP, unsupported: [{ request_quote: '', reason: 'x', requires: [] }] },
      { ...CAFEMAP, external: [{ ...CAFEMAP.external[0], needs: ['password'] }] },
      { ...CAFEMAP, external: [{ ...CAFEMAP.external[0], status: 'maybe' }] },
      { ...CAFEMAP, request_digest: 'nope' },
    ]
    for (const support of bad) {
      expect(validPlan({ ...PLAN_VIEW, support })).toBe(false)
      expect(isPlanSupport(support)).toBe(false)
      expect(isPlanView({ ...PLAN_VIEW, support })).toBe(false)
    }
  })
})

describe('기획 승인 화면의 지원 공백 구역', () => {
  test('공백이 있으면 요청 인용·이유·필요 입력·외부 의존을 따로 보여 주고 승인을 막는다(거절은 유지)', async () => {
    const { w, send } = dialog({ ...PLAN_VIEW, support: CAFEMAP })
    await flushPromises()
    const region = w.find('section[aria-label="지원 범위와 공백"]')
    expect(region.exists()).toBe(true)
    const text = region.text()
    expect(text).toContain('카공지도(cafemap-v1)')
    expect(text).toContain('“내 위치를 기반으로 주변 카페를 추천”')
    expect(text).toContain('장소 데이터 공급자가 정해지지 않았습니다.')
    expect(text).toContain('위치 동의 경로')
    expect(text).toContain('공급자 미정')
    expect(text).toContain('보류')
    expect(text).toContain('무료 자격')
    expect(text).toContain('위치 동의')
    expect(text).toContain('현재 공백 때문에 구현 승인을 보낼 수 없습니다')
    expect(button(w, '이 기획으로 구현 시작').attributes('disabled')).toBeDefined()
    await w.find('textarea').setValue('지도 없이 수동 위치 입력으로 다시 기획해 주세요')
    expect(button(w, '수정 요청(거절)').attributes('disabled')).toBeUndefined()
    await button(w, '수정 요청(거절)').trigger('click')
    await flushPromises()
    expect(send).toHaveBeenCalledOnce()
    w.unmount()
  })

  test('알려진 공백이 없으면 승인할 수 있고, 그것이 AC 충족이나 출시 수용이 아님을 밝힌다', async () => {
    const support: Support = { ...CAFEMAP, template_id: 'requests-v1', implementation_allowed: true, unsupported: [], external: [] }
    const { w } = dialog({ ...PLAN_VIEW, support })
    await flushPromises()
    const text = w.find('section[aria-label="지원 범위와 공백"]').text()
    expect(text).toContain('알려진 지원 공백 없음')
    expect(text).toContain('AC 충족이나 검토·출시 수용을 뜻하지 않습니다')
    expect(button(w, '이 기획으로 구현 시작').attributes('disabled')).toBeUndefined()
    w.unmount()
  })

  test('support가 없으면 지원 완료로 추정하지 않고 미제공·미확인으로 표시한다', async () => {
    const { support: _omit, ...plain } = { ...PLAN_VIEW, support: undefined }
    const { w } = dialog(plain)
    await flushPromises()
    expect(w.find('section[aria-label="지원 범위와 공백"]').text()).toContain('지원 정보 미제공 · 미확인')
    w.unmount()
  })

  test('support의 명세 버전이 기획과 다르면 표시·승인을 막고 다시 읽는다', async () => {
    const getArtifact = vi.fn(async () => ({ ...PLAN_VIEW, support: { ...CAFEMAP, implementation_allowed: true, unsupported: [], external: [], spec_version_id: 'spec-old' } }))
    const source = { ...exampleSource(scenario), getArtifact }
    const w = mount(PlanApprovalDialog, {
      attachTo: document.body,
      props: { open: true, approval: pendingApproval(scenario.snapshot, 'plan'), specArtifactId: 'a-spec', source, runId: 'r1', readOnly: false, send: vi.fn() },
    })
    await flushPromises()
    const text = w.find('section[aria-label="지원 범위와 공백"]').text()
    expect(text).toContain('지원 정보의 명세 버전(spec-old)이 기획과 달라 표시하지 않습니다')
    expect(text).not.toContain('알려진 지원 공백 없음')
    expect(button(w, '이 기획으로 구현 시작').attributes('disabled')).toBeDefined()
    await button(w, '다시 읽기').trigger('click')
    await flushPromises()
    expect(getArtifact).toHaveBeenCalledTimes(2)
    w.unmount()
  })
})
