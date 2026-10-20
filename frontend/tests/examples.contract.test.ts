import Ajv2020 from 'ajv/dist/2020'
import addFormats from 'ajv-formats'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, test } from 'vitest'
import { SCENARIOS } from '../src/examples/scenarios'
import { PLAN_VIEW } from '../src/examples/base'

const dir = resolve(__dirname, '../../docs/planning')
const protocol = JSON.parse(readFileSync(resolve(dir, 'protocol.v1.schema.json'), 'utf8'))
const http = JSON.parse(readFileSync(resolve(dir, 'http.v1.schema.json'), 'utf8'))

const ajv = new Ajv2020({ strict: false, allErrors: true })
addFormats(ajv)
ajv.addSchema(protocol, 'protocol.v1.schema.json')
ajv.addSchema(http, 'http.v1.schema.json')

const check = (ref: string, value: unknown) => {
  const validate = ajv.getSchema(ref)
  if (!validate) throw new Error(`schema ${ref} not found`)
  const ok = validate(value)
  return ok ? [] : (validate.errors ?? []).map((e) => `${e.instancePath} ${e.message}`)
}

describe('합성 예시는 공유 계약을 따른다', () => {
  test.each(SCENARIOS.map((s) => [s.id, s]))('%s 스냅샷이 protocol.Snapshot에 맞는다', (_id, s) => {
    expect(check('protocol.v1.schema.json#/$defs/Snapshot', s.snapshot)).toEqual([])
  })

  test.each(SCENARIOS.map((s) => [s.id, s]))('%s 사건이 protocol.Event에 맞고 seq가 연속이다', (_id, s) => {
    const all = [...s.events, ...s.tail]
    all.forEach((e, i) => {
      expect(check('protocol.v1.schema.json#/$defs/Event', e)).toEqual([])
      expect(e.seq).toBe(i + 1)
    })
    expect(s.snapshot.last_event_seq).toBe(s.events.length)
    expect(all.every((e) => e.state_version <= s.snapshot.state_version)).toBe(true)
  })

  test('기획 본문은 http.PlanView에 맞는다', () => {
    expect(check('http.v1.schema.json#/$defs/PlanView', PLAN_VIEW)).toEqual([])
  })

  test('환경 예시는 http.Environment에 맞는다', () => {
    SCENARIOS.flatMap((s) => Object.values(s.environments)).forEach((env) => {
      expect(check('http.v1.schema.json#/$defs/Environment', env)).toEqual([])
    })
  })

  test('작업·사건·승인이 참조하는 ID가 스냅샷 안에 존재한다', () => {
    for (const s of SCENARIOS) {
      const taskIds = new Set(s.snapshot.tasks.map((t) => t.id))
      const sprintIds = new Set(s.snapshot.sprints.map((sp) => sp.id))
      s.snapshot.tasks.forEach((t) => {
        expect(sprintIds.has(t.sprint_id)).toBe(true)
        t.depends_on.forEach((d) => expect(taskIds.has(d)).toBe(true))
      })
      s.events.forEach((e) => e.task_id && expect(taskIds.has(e.task_id)).toBe(true))
      const reportIds = new Set(s.snapshot.reports.map((r) => r.id))
      s.snapshot.approvals.forEach((a) => {
        if (a.target.gate === 'release') a.target.review_report_ids.forEach((id) => expect(reportIds.has(id)).toBe(true))
      })
    }
  })

  test('예시는 실제 기록 재생으로 가장하지 않는다 (replay_source 없음)', () => {
    SCENARIOS.forEach((s) => {
      expect(s.snapshot.mode).toBe('live')
      expect('replay_source' in s.snapshot).toBe(false)
    })
  })
})
