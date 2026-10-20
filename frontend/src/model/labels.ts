import type { ReviewReport, Role, RunEvent, RunState, TaskState, WorkKind } from '../api/types'

/** 상태는 색만으로 구분하지 않는다: 기호 + 한글 이름 + 톤(색 토큰) */
export type Tone = 'neutral' | 'active' | 'ok' | 'warn' | 'danger' | 'wait'

export interface StateLabel {
  text: string
  glyph: string
  tone: Tone
}

export const RUN_STATE: Record<RunState, StateLabel> = {
  planning: { text: '기획 중', glyph: '✎', tone: 'active' },
  awaiting_plan_approval: { text: '기획 승인 대기', glyph: '⚑', tone: 'warn' },
  building: { text: '구현 중', glyph: '●', tone: 'active' },
  reviewing: { text: '검증·보안 검토 중', glyph: '◎', tone: 'active' },
  preview_ready: { text: '프리뷰 확인 대기', glyph: '⚑', tone: 'warn' },
  awaiting_release_approval: { text: '배포 승인 대기', glyph: '⚑', tone: 'warn' },
  deploying: { text: '배포 중', glyph: '▲', tone: 'active' },
  succeeded: { text: '완료', glyph: '✓', tone: 'ok' },
  paused: { text: '일시 중지됨', glyph: '❙❙', tone: 'wait' },
  waiting_resource: { text: '자원 대기', glyph: '◷', tone: 'wait' },
  waiting_quota: { text: '무료 한도 대기', glyph: '◷', tone: 'wait' },
  needs_input: { text: '입력 필요', glyph: '?', tone: 'warn' },
  failed: { text: '실패', glyph: '✕', tone: 'danger' },
  cancelled: { text: '취소됨', glyph: '■', tone: 'neutral' },
}

export const TASK_STATE: Record<TaskState, StateLabel> = {
  pending: { text: '대기', glyph: '○', tone: 'neutral' },
  ready: { text: '착수 가능', glyph: '◌', tone: 'neutral' },
  running: { text: '진행 중', glyph: '●', tone: 'active' },
  succeeded: { text: '완료', glyph: '✓', tone: 'ok' },
  failed: { text: '실패', glyph: '✕', tone: 'danger' },
  blocked: { text: '차단', glyph: '⊘', tone: 'danger' },
  cancelled: { text: '취소', glyph: '■', tone: 'neutral' },
  superseded: { text: '대체됨', glyph: '↷', tone: 'neutral' },
}

export const VERDICT: Record<ReviewReport['verdict'], StateLabel> = {
  pass: { text: '통과', glyph: '✓', tone: 'ok' },
  fail: { text: '실패', glyph: '✕', tone: 'danger' },
  error: { text: '검사 오류', glyph: '!', tone: 'danger' },
  not_run: { text: '미실행', glyph: '–', tone: 'warn' },
  inconclusive: { text: '판정 불가', glyph: '?', tone: 'warn' },
}

export const ROLE: Record<Role, { text: string; glyph: string }> = {
  supervisor: { text: '감독', glyph: 'S' },
  planner: { text: '기획', glyph: 'P' },
  builder: { text: '구현', glyph: 'B' },
  validator: { text: '검증', glyph: 'V' },
  security: { text: '보안', glyph: '⛨' },
  release: { text: '출시', glyph: 'R' },
}

export const WORK_KIND: Record<WorkKind, string> = {
  planning: '기획',
  contract: '계약',
  infra: '인프라',
  backend: '백엔드',
  frontend: '프론트',
  ai_data: 'AI·데이터',
  integration: '통합',
  validation: '검증',
  security: '보안',
  release: '출시',
}

export const EVENT_TYPE: Record<RunEvent['event_type'], string> = {
  run_state_changed: '실행 상태 변경',
  plan_proposed: '기획안 제시',
  approval_requested: '승인 요청',
  approval_decided: '승인 결정',
  approval_invalidated: '승인 무효화',
  task_started: '작업 시작',
  task_finished: '작업 종료',
  tool_finished: '도구 실행 결과',
  retrieval_finished: '검색 결과',
  context_saved: '문맥 저장',
  review_submitted: '검토 보고서 제출',
  preview_ready: '프리뷰 준비',
  changes_requested: '수정 요청',
  resource_wait: '자원 대기',
  quota_wait: '무료 한도 대기',
  deployment_started: '배포 시작',
  deployment_finished: '배포 종료',
  operation_uncertain: '외부 작업 결과 불명',
  warning: '경고',
}

/** 사건 기록에서 점수와 무관하게 강조할 사건 */
export const CRITICAL_EVENTS = new Set<RunEvent['event_type']>([
  'approval_requested', 'approval_invalidated', 'quota_wait', 'resource_wait', 'operation_uncertain', 'warning',
])

export function shortDigest(value: string | null | undefined): string {
  if (!value) return '—'
  const hex = value.replace(/^sha256:/, '')
  return value.startsWith('sha256:') ? `sha256:${hex.slice(0, 12)}…` : `${hex.slice(0, 12)}…`
}

export function formatTime(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('ko-KR', { hour12: false })
}
