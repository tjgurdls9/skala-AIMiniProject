// DEV-P03/S07 화면: 두 검토의 독립 판정·대상 일치, 현재/과거 회차
import { mount } from '@vue/test-utils'
import { describe, expect, test } from 'vitest'
import type { ReviewReport, Snapshot } from '../src/api/types'
import ReviewPair from '../src/components/ReviewPair.vue'
import ReviewRounds from '../src/components/ReviewRounds.vue'
import { fakeCommit, fakeDigest, report, SPEC_V2 } from '../src/examples/base'
import { findScenario } from '../src/examples/scenarios'
import { reviewRounds, roundOutcome, sameTarget } from '../src/model/reviews'

const base = findScenario('preview')!.snapshot
const withReports = (reports: ReviewReport[]): Snapshot => ({ ...base, reports })
const older = (r: ReviewReport, id: string): ReviewReport => ({ ...r, id, commit_sha: fakeCommit('aa'), image_digest: fakeDigest('a9') })

describe('검토 회차', () => {
  test('후보별로 회차를 묶고 마지막만 현재 회차로 본다', () => {
    const reports = [
      older(report('validator', 'pass'), 'old-v'),
      older(report('security', 'fail'), 'old-s'),
      report('validator', 'pass'),
      report('security', 'pass'),
    ]
    const rounds = reviewRounds(withReports(reports))
    expect(rounds.map((r) => [r.isCurrent, roundOutcome(r)])).toEqual([[false, 'blocked'], [true, 'both_pass']])
  })

  test('같은 후보를 다시 검토하면 새 회차로 남기고 옛 원본을 지우지 않는다', () => {
    const reports = [report('validator', 'not_run', 'v1'), report('security', 'pass', 's1'), report('validator', 'pass', 'v2'), report('security', 'pass', 's2')]
    const rounds = reviewRounds(withReports(reports))
    expect(rounds.map((r) => [r.validator?.id, r.security?.id])).toEqual([['v1', 's1'], ['v2', 's2']])
    expect(roundOutcome(rounds[0])).toBe('blocked')
  })

  test('한쪽만 있으면 대기, 한쪽 통과는 통과가 아니다', () => {
    const [waiting] = reviewRounds(withReports([report('validator', 'pass')]))
    expect(roundOutcome(waiting)).toBe('waiting')
    const [split] = reviewRounds(withReports([report('validator', 'pass'), report('security', 'inconclusive')]))
    expect(roundOutcome(split)).toBe('blocked')
  })

  test('현재 명세와 다른 명세의 회차를 표시한다', () => {
    const [round] = reviewRounds(withReports([{ ...report('validator', 'pass'), spec_version_id: SPEC_V2 }]))
    expect(round.specMatches).toBe(false)
    const w = mount(ReviewRounds, { props: { snapshot: withReports([{ ...report('validator', 'pass'), spec_version_id: SPEC_V2 }]) } })
    expect(w.text()).toContain('현재 명세와 다름')
    expect(w.text()).toContain('다른 검토 제출 대기')
  })

  test('회차 화면은 현재·과거를 구분하고 과거 원본도 연다', async () => {
    const w = mount(ReviewRounds, { props: { snapshot: withReports([older(report('validator', 'pass'), 'ov'), older(report('security', 'fail'), 'os'), report('validator', 'pass'), report('security', 'pass')]) } })
    const text = w.text()
    expect(text.indexOf('현재 회차')).toBeLessThan(text.indexOf('과거 회차'))
    expect(text).toContain('출시 차단')
    await w.findAll('button').at(-1)!.trigger('click')
    expect(w.emitted('artifact')).toEqual([['a-security']])
    expect(mount(ReviewRounds, { props: { snapshot: withReports([]) } }).text()).toContain('아직 제출된 검토 보고서가 없습니다')
  })
})

describe('두 보고서의 대상 일치', () => {
  test('명세·커밋·이미지가 모두 같아야 같은 후보로 본다', () => {
    const v = report('validator', 'pass')
    expect(sameTarget(v, report('security', 'pass'))).toBe(true)
    expect(sameTarget(v, { ...report('security', 'pass'), image_digest: fakeDigest('ff') })).toBe(false)
    expect(sameTarget(v, null)).toBe(false)
  })

  test('대상이 다르면 경고하고, 같으면 판정을 각자 보라고 안내한다', () => {
    const mismatch = mount(ReviewPair, { props: { pair: { validator: report('validator', 'pass'), security: { ...report('security', 'pass'), commit_sha: fakeCommit('ee') } } } })
    expect(mismatch.text()).toContain('서로 다른 명세·커밋·이미지')
    const same = mount(ReviewPair, { props: { pair: { validator: report('validator', 'pass'), security: report('security', 'fail') } } })
    expect(same.text()).toContain('판정은 각자 따로')
    expect(same.text()).toContain('✓ 통과')
    expect(same.text()).toContain('✕ 실패')
  })
})
