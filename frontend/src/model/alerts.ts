import type { Snapshot } from '../api/types'
import { pendingApproval, reviewPair } from './derive'
import { VERDICT, type Tone } from './labels'

export type AlertAction = { kind: 'plan' } | { kind: 'release' } | { kind: 'preview' } | { kind: 'task'; taskId: string }

export interface Alert {
  key: string
  tone: Tone
  glyph: string
  text: string
  action?: AlertAction
}

/**
 * 관련도 점수와 무관하게 고정 노출할 항목: 승인 대기·실패·보안 차단·무료 소진·자원 대기·입력 필요.
 * 순서는 고정(재정렬로 버튼 위치가 바뀌지 않게)한다.
 */
export function runAlerts(snapshot: Snapshot): Alert[] {
  const alerts: Alert[] = []
  if (pendingApproval(snapshot, 'plan')) {
    alerts.push({ key: 'plan', tone: 'warn', glyph: '⚑', text: '기획 승인 대기 — 승인 전에는 구현이 시작되지 않습니다', action: { kind: 'plan' } })
  }
  if (snapshot.state === 'preview_ready') {
    alerts.push({ key: 'preview', tone: 'warn', glyph: '⚑', text: '프리뷰 확인 대기 — 수정 요청 또는 다음 단계를 결정하세요', action: { kind: 'preview' } })
  }
  if (pendingApproval(snapshot, 'release')) {
    alerts.push({ key: 'release', tone: 'warn', glyph: '⚑', text: '배포 승인 대기 — 고정된 커밋·이미지·환경을 확인하세요', action: { kind: 'release' } })
  }
  const pair = reviewPair(snapshot)
  for (const report of [pair.validator, pair.security]) {
    if (report && report.verdict !== 'pass') {
      const who = report.role === 'validator' ? '검증' : '보안'
      alerts.push({ key: `report-${report.id}`, tone: 'danger', glyph: '⛔', text: `${who} ${VERDICT[report.verdict].text} — 출시 차단` })
    }
  }
  if (snapshot.state === 'waiting_quota') alerts.push({ key: 'quota', tone: 'wait', glyph: '◷', text: `무료 한도 대기 — 유료 전환 없음${snapshot.reason ? ` · ${snapshot.reason}` : ''}` })
  if (snapshot.state === 'waiting_resource') alerts.push({ key: 'resource', tone: 'wait', glyph: '◷', text: `자원 대기${snapshot.reason ? ` · ${snapshot.reason}` : ''}` })
  if (snapshot.state === 'needs_input') alerts.push({ key: 'input', tone: 'warn', glyph: '?', text: `입력 필요${snapshot.reason ? ` · ${snapshot.reason}` : ''}` })
  if (snapshot.state === 'failed') alerts.push({ key: 'failed', tone: 'danger', glyph: '✕', text: `실행 실패${snapshot.reason ? ` · ${snapshot.reason}` : ''}` })
  for (const task of snapshot.tasks) {
    if (task.state === 'failed' || task.state === 'blocked') {
      alerts.push({
        key: `task-${task.id}`,
        tone: 'danger',
        glyph: task.state === 'failed' ? '✕' : '⊘',
        text: `${task.title} ${task.state === 'failed' ? '실패' : '차단'}${task.reason ? ` · ${task.reason}` : ''}`,
        action: { kind: 'task', taskId: task.id },
      })
    }
  }
  return alerts
}
