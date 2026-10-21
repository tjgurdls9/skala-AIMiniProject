import type { Role } from '../api/types'

/** 업무 흐름 순서: 명세 회의실 → 구현 구역 → 분리된 검증실·보안실 → 출시 게이트 */
export type ZoneId = 'meeting' | 'build' | 'validate' | 'security' | 'release'

export const ZONE_LABEL: Record<ZoneId, string> = {
  meeting: '명세 회의실',
  build: '구현 구역',
  validate: '검증실',
  security: '보안실',
  release: '출시 게이트',
}

export const ROLE_ZONE: Record<Role, ZoneId> = {
  supervisor: 'meeting',
  planner: 'meeting',
  builder: 'build',
  validator: 'validate',
  security: 'security',
  release: 'release',
}
