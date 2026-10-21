import type { AcceptanceTarget, Approval, ReleaseTarget, Snapshot } from '../api/types'
import type { StateLabel } from './labels'
import { reviewPair, type ReviewPair } from './derive'

// CR-C18 사람 확인 AC의 승인(gate "acceptance"). 계약: Codex db1300f.
// 승인은 사용자 조작으로만 생긴다. 사람 확인 AC의 판정(not_run)은 승인으로 met가 되지 않으므로 이 모듈은 판정을 건드리지 않는다.

export type AcceptanceApproval = Approval & { target: AcceptanceTarget }
export type ManualState = 'pending' | 'approved' | 'rejected'

export const MANUAL_STATE: Record<ManualState, StateLabel> = {
  pending: { text: '사람 확인 대기', glyph: '⚑', tone: 'warn' },
  approved: { text: '사람 확인 승인됨', glyph: '✓', tone: 'ok' },
  rejected: { text: '사람 확인 거절됨', glyph: '✕', tone: 'danger' },
}

const isAcceptance = (a: Approval): a is AcceptanceApproval => a.target.gate === 'acceptance'

/** 무효 포함, 스냅샷의 모든 사람 확인 승인 */
export function acceptanceApprovals(snapshot: Snapshot): AcceptanceApproval[] {
  return snapshot.approvals.filter(isAcceptance)
}

/** 화면이 다룰 승인: 대기 중인 것, 없으면 마지막 결정. 무효(invalidated)는 새 후보에 쓸 수 없어 제외한다 */
export function currentAcceptance(snapshot: Snapshot): AcceptanceApproval | null {
  const live = acceptanceApprovals(snapshot).filter((a) => a.state !== 'invalidated')
  return live.find((a) => a.state === 'pending') ?? live.at(-1) ?? null
}

/** 대상이 현재 후보(두 보고서가 검토한 커밋·이미지, 검증 보고서)와 다른 이유. 같으면 null */
export function acceptanceMismatch(target: AcceptanceTarget, pair: ReviewPair): string | null {
  const { validator, security } = pair
  if (!validator || !security) return '현재 후보의 검증·보안 보고서가 모두 없어 승인 대상이 현재 후보인지 확인할 수 없습니다.'
  if ([validator, security].some((r) => r.commit_sha !== target.commit_sha || r.image_digest !== target.image_digest)) {
    return '승인 대상의 커밋·이미지가 현재 후보와 다릅니다.'
  }
  if (validator.spec_version_id !== target.spec_version_id) return '승인 대상의 명세 버전이 현재 검증 보고서와 다릅니다.'
  if (validator.id !== target.validator_report_id || validator.content_digest !== target.validator_report_digest) {
    return '승인 대상이 가리키는 검증 보고서가 현재 보고서와 다릅니다.'
  }
  return null
}

/** AC id별 사람 확인 상태. 현재 후보와 일치하는 승인만 붙이고, 판정(AcceptanceStatus)은 바꾸지 않는다 */
export function manualAcStates(snapshot: Snapshot): Map<string, ManualState> {
  const current = currentAcceptance(snapshot)
  if (!current || acceptanceMismatch(current.target, reviewPair(snapshot))) return new Map()
  return new Map(current.target.ac_ids.map((id) => [id, current.state as ManualState]))
}

/** 검증 보고서 본문의 manual_pending(사람 확인 AC id 목록). 문자열 배열이 아니면 null */
export function manualPendingOf(body: unknown): string[] | null {
  if (!body || typeof body !== 'object') return null
  const list = (body as { manual_pending?: unknown }).manual_pending
  return Array.isArray(list) && list.every((v) => typeof v === 'string') ? list : null
}

export type ReleaseAcceptanceGate =
  | { kind: 'none' }
  | { kind: 'ok'; approval: AcceptanceApproval }
  | { kind: 'blocked'; reason: string; approval: AcceptanceApproval | null }

const STATE_TEXT: Record<Approval['state'], string> = { pending: '대기 중', approved: '승인됨', rejected: '거절됨', invalidated: '무효' }

/**
 * 배포 승인에서 사람 확인 승인이 어떻게 걸리는가. 최종 판단은 서버가 한다.
 * - none: 사람 확인 승인 기록이 없다(사람 확인 AC가 없거나 옛 기록). 표시하지 않는다.
 * - ok: 배포 대상이 가리키는 승인이 승인됨이고 후보가 같다.
 * - blocked: 대기·거절·무효·없음·후보 불일치·연결 누락.
 */
export function releaseAcceptanceGate(snapshot: Snapshot, target: ReleaseTarget): ReleaseAcceptanceGate {
  const linkedId = target.acceptance_approval_id
  if (linkedId) {
    const linked = acceptanceApprovals(snapshot).find((a) => a.id === linkedId) ?? null
    if (!linked) return { kind: 'blocked', reason: '배포 대상이 연결한 사람 확인 승인을 찾을 수 없습니다.', approval: null }
    if (linked.state !== 'approved') return { kind: 'blocked', reason: `사람 확인 승인이 아직 승인되지 않았습니다(${STATE_TEXT[linked.state]}).`, approval: linked }
    if (linked.target.commit_sha !== target.commit_sha || linked.target.image_digest !== target.image_digest) {
      return { kind: 'blocked', reason: '사람 확인 승인의 커밋·이미지가 배포 대상과 다릅니다.', approval: linked }
    }
    return { kind: 'ok', approval: linked }
  }
  const current = currentAcceptance(snapshot)
  if (!current) return { kind: 'none' }
  if (current.state === 'approved') return { kind: 'blocked', reason: '사람 확인 승인은 있지만 배포 대상이 그 승인에 연결되지 않았습니다.', approval: current }
  return { kind: 'blocked', reason: `사람 확인 승인이 아직 승인되지 않았습니다(${STATE_TEXT[current.state]}).`, approval: current }
}
