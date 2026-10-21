import { describe, expect, test } from 'vitest'
import { ApiError, errorHint, toApiError } from '../src/api/errors'
import { findScenario, SCENARIOS } from '../src/examples/scenarios'
import { buildEvents } from '../src/examples/base'
import {
  bothPassed, deriveCurrentSprintId, indexById, isRunActive, isStoppable, orderedPhases, pendingApproval,
  reviewPair, tallySprint, waitingReason,
} from '../src/model/derive'
import { classifyEvent, needsSnapshot, parseEventData } from '../src/model/eventStream'
import { formatTime, shortDigest } from '../src/model/labels'
import { eventEmphasis, groupRepeats, relatedTaskIds } from '../src/model/relevance'

const scenario = (id: string) => {
  const s = findScenario(id)
  if (!s) throw new Error(id)
  return s
}

describe('사건 수신 판정', () => {
  test('이미 받은 seq는 중복으로 버린다', () => {
    expect(classifyEvent(5, { seq: 5 })).toEqual({ kind: 'duplicate' })
    expect(classifyEvent(5, { seq: 3 })).toEqual({ kind: 'duplicate' })
  })
  test('다음 seq만 추가한다', () => {
    expect(classifyEvent(5, { seq: 6 })).toEqual({ kind: 'append' })
  })
  test('건너뛴 seq는 누락으로 판정한다', () => {
    expect(classifyEvent(5, { seq: 9 })).toEqual({ kind: 'gap', expected: 6, got: 9 })
  })
  test('더 새 상태 버전 사건이면 스냅샷을 다시 읽는다', () => {
    expect(needsSnapshot({ last_event_seq: 10 }, { seq: 11 })).toBe(true)
    expect(needsSnapshot({ last_event_seq: 10 }, { seq: 10 })).toBe(false) // 스냅샷에 이미 반영된 사건
    expect(needsSnapshot(null, { seq: 1 })).toBe(true)
  })
  test('SSE data는 같은 실행의 protocol.Event 형태만 받는다', () => {
    const [event] = buildEvents([['warning', '경고', {}]])
    expect(parseEventData(JSON.stringify(event), event.run_id)).toEqual(event)
    expect(parseEventData(JSON.stringify(event), 'other-run')).toBeNull()
    expect(parseEventData('{bad', event.run_id)).toBeNull()
    expect(parseEventData(JSON.stringify({ ...event, seq: 0 }), event.run_id)).toBeNull()
    expect(parseEventData(JSON.stringify({ ...event, summary: 1 }), event.run_id)).toBeNull()
    expect(parseEventData(JSON.stringify({ reason: 'cursor_out_of_range' }), event.run_id)).toBeNull()
  })
})

describe('파생 계산', () => {
  test('현재 Sprint는 running 작업이 있는 Sprint에서 도출한다', () => {
    expect(deriveCurrentSprintId(scenario('building').snapshot)).toBe('sp-2')
  })
  test('running이 없으면 ready → 실패·차단 → 대기 순, 모두 끝났으면 마지막 Sprint', () => {
    expect(deriveCurrentSprintId(scenario('review-split').snapshot)).toBe('sp-3')
    expect(deriveCurrentSprintId(scenario('failed').snapshot)).toBe('sp-3')
    expect(deriveCurrentSprintId(scenario('release-approval').snapshot)).toBe('sp-5')
    expect(deriveCurrentSprintId(scenario('succeeded').snapshot)).toBe('sp-5')
    expect(deriveCurrentSprintId({ ...scenario('succeeded').snapshot, sprints: [] })).toBeNull()
  })
  test('Sprint 집계는 작업 상태별 수와 AC 정의 수만 낸다', () => {
    const snap = scenario('building').snapshot
    const tally = tallySprint(snap, snap.sprints[1])
    expect(tally).toEqual({ total: 4, succeeded: 2, running: 1, failed: 0, blocked: 1, waiting: 0, closed: 0, acceptanceCount: 2 })
  })
  test('대기 이유는 서버 reason을 우선하고 없으면 끝나지 않은 선행 작업을 나열한다', () => {
    const snap = scenario('building').snapshot
    const byId = indexById(snap.tasks)
    expect(waitingReason(byId.get('t-infra')!, byId)).toBe('컨테이너 실행기 미연결 — 자원 준비 필요')
    expect(waitingReason(byId.get('t-ui')!, byId)).toBe('선행 작업 대기: 할 일 조회·상태 변경 API')
    expect(waitingReason(byId.get('t-api')!, byId)).toBeNull()
    expect(waitingReason(byId.get('t-plan')!, byId)).toBeNull()
  })
  test('Phase는 order 순으로 정렬한다', () => {
    const snap = scenario('building').snapshot
    const reversed = { ...snap, phases: [...snap.phases].reverse() }
    expect(orderedPhases(reversed).map((p) => p.id)).toEqual(['ph-plan', 'ph-build', 'ph-review', 'ph-release'])
  })
  test('대기 중인 승인만 게이트별로 찾는다', () => {
    expect(pendingApproval(scenario('plan-approval').snapshot, 'plan')?.id).toBe('ap-plan-1')
    expect(pendingApproval(scenario('release-approval').snapshot, 'release')?.id).toBe('ap-release-2')
    expect(pendingApproval(scenario('building').snapshot, 'plan')).toBeNull()
  })
  test('한쪽 검토만 통과하면 전체 통과가 아니다', () => {
    const split = reviewPair(scenario('review-split').snapshot)
    expect(split.validator?.verdict).toBe('pass')
    expect(split.security?.verdict).toBe('fail')
    expect(bothPassed(split)).toBe(false)
    expect(bothPassed(reviewPair(scenario('preview').snapshot, ['rp-validator', 'rp-security']))).toBe(true)
    expect(bothPassed(reviewPair(scenario('building').snapshot))).toBe(false)
  })
  test('종료 상태에서는 중지할 수 없고 진행 상태는 활성이다', () => {
    expect(isStoppable('succeeded')).toBe(false)
    expect(isStoppable('paused')).toBe(true)
    expect(isRunActive('building')).toBe(true)
    expect(isRunActive('awaiting_plan_approval')).toBe(false)
  })
})

describe('로컬 관련도 보조', () => {
  const snap = scenario('building').snapshot
  test('관심 분야 작업과 직접 의존 관계의 작업을 관련으로 본다', () => {
    const related = relatedTaskIds(snap.tasks, new Set(['frontend']))
    expect([...related].sort()).toEqual(['t-api', 't-int', 't-ui'])
  })
  test('승인 대기·한도 대기 같은 사건은 점수와 무관하게 critical', () => {
    const events = scenario('quota').events
    const quota = events.find((e) => e.event_type === 'quota_wait')!
    expect(eventEmphasis(quota, new Set())).toBe('critical')
    const started = events.find((e) => e.event_type === 'task_started' && e.task_id === 't-api')!
    expect(eventEmphasis(started, new Set(['t-api']))).toBe('related')
    expect(eventEmphasis(started, new Set())).toBe('none')
  })
  test('연속된 같은 종류·같은 작업 사건만 순서를 유지하며 묶는다', () => {
    const events = buildEvents([
      ['tool_finished', 'a', { task_id: 't-api' }],
      ['tool_finished', 'b', { task_id: 't-api' }],
      ['tool_finished', 'c', { task_id: 't-ui' }],
      ['warning', 'w1', {}],
      ['warning', 'w2', {}],
    ])
    const groups = groupRepeats(events)
    expect(groups.map((g) => [g.first.summary, g.last.summary, g.count])).toEqual([
      ['a', 'b', 2], ['c', 'c', 1], ['w1', 'w1', 1], ['w2', 'w2', 1],
    ])
  })
})

describe('오류 모델', () => {
  test('http.Error 본문의 코드·메시지·현재 버전을 읽는다', () => {
    const err = toApiError(409, { error: { code: 'STALE_APPROVAL', message: '대상 변경', current_state_version: 7 } })
    expect([err.code, err.message, err.currentStateVersion, err.isStale]).toEqual(['STALE_APPROVAL', '대상 변경', 7, true])
  })
  test('형식이 다른 본문은 신뢰하지 않는다', () => {
    expect(toApiError(500, { detail: 'x' }).code).toBe('BAD_RESPONSE')
    expect(toApiError(500, null).code).toBe('BAD_RESPONSE')
    expect(toApiError(409, { error: { code: 'MADE_UP', message: 'x' } }).code).toBe('BAD_RESPONSE')
    expect(toApiError(409, { error: { code: 'COMMAND_CONFLICT', message: '' } }).message).toBe('요청 실패 (409)')
  })
  test('본문 없는 게이트웨이 오류는 연결 실패로, http.Error가 있으면 그 코드로 본다', () => {
    expect(toApiError(502, null).code).toBe('NETWORK')
    expect(toApiError(503, { error: { code: 'TEMPORARILY_UNAVAILABLE', message: '점검' } }).code).toBe('TEMPORARILY_UNAVAILABLE')
  })
  test('모든 코드에 다음 행동 안내가 있다', () => {
    const codes = ['VERSION_CONFLICT', 'COMMAND_CONFLICT', 'REPLAY_READ_ONLY', 'RUNTIME_UNAVAILABLE', 'UNAUTHORIZED', 'NETWORK', 'EXAMPLE_NOOP', 'NOT_FOUND'] as const
    codes.forEach((c) => expect(errorHint(new ApiError(0, c, 'm')).length).toBeGreaterThan(5))
  })
})

describe('표시 도우미', () => {
  test('digest는 접두어를 유지한 채 줄인다', () => {
    expect(shortDigest(`sha256:${'ab'.repeat(32)}`)).toBe('sha256:abababababab…')
    expect(shortDigest('cd'.repeat(20))).toBe('cdcdcdcdcdcd…')
    expect(shortDigest(null)).toBe('—')
  })
  test('잘못된 시각은 원문 그대로 보여준다', () => {
    expect(formatTime('not-a-date')).toBe('not-a-date')
    expect(formatTime('2026-10-20T00:00:00Z')).toMatch(/2026/)
  })
  test('시나리오 ID 조회', () => {
    expect(findScenario('nope')).toBeNull()
    expect(SCENARIOS.length).toBeGreaterThanOrEqual(9)
  })
})
