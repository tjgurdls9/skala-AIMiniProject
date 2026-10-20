import type { ReviewReport, Snapshot } from '../api/types'

/** 같은 후보(명세·커밋·이미지)를 대상으로 한 검토 한 회차. 두 판정은 합치지 않고 각자 보존한다. */
export interface ReviewRound {
  key: string
  spec: string
  commit: string
  image: string
  validator: ReviewReport | null
  security: ReviewReport | null
  /** 가장 최근 회차인가(그 외는 과거 회차) */
  isCurrent: boolean
  /** 회차의 명세가 실행의 현재 명세와 같은가 */
  specMatches: boolean
}

const keyOf = (r: ReviewReport) => `${r.spec_version_id}|${r.commit_sha}|${r.image_digest}`

/** 보고서 순서를 따라 후보별 회차로 묶는다. 같은 후보에 같은 역할이 다시 오면 새 회차로 본다. */
export function reviewRounds(snapshot: Snapshot): ReviewRound[] {
  const rounds: ReviewRound[] = []
  for (const report of snapshot.reports) {
    const key = keyOf(report)
    const open = [...rounds].reverse().find((r) => r.key === key && r[report.role] === null)
    if (open) {
      const i = rounds.indexOf(open)
      rounds[i] = { ...open, [report.role]: report }
    } else {
      rounds.push({
        key,
        spec: report.spec_version_id,
        commit: report.commit_sha,
        image: report.image_digest,
        validator: report.role === 'validator' ? report : null,
        security: report.role === 'security' ? report : null,
        isCurrent: false,
        specMatches: report.spec_version_id === snapshot.spec_version_id,
      })
    }
  }
  return rounds.map((r, i) => ({ ...r, isCurrent: i === rounds.length - 1 }))
}

/** 회차 판정 요약: 둘 다 통과일 때만 '두 검토 통과'. 한쪽 통과는 통과가 아니다. */
export function roundOutcome(round: ReviewRound): 'both_pass' | 'blocked' | 'waiting' {
  const { validator, security } = round
  if (!validator || !security) return 'waiting'
  return validator.verdict === 'pass' && security.verdict === 'pass' ? 'both_pass' : 'blocked'
}

/** 두 보고서가 같은 명세·커밋·이미지를 검토했는가. 다르면 같은 후보의 판정으로 묶을 수 없다. */
export function sameTarget(a: ReviewReport | null, b: ReviewReport | null): boolean {
  return !!a && !!b && a.spec_version_id === b.spec_version_id && a.commit_sha === b.commit_sha && a.image_digest === b.image_digest
}
