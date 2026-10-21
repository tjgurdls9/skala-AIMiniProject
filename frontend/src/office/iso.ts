import type { RunEvent, Task } from '../api/types'
import { ROLE_ZONE, ZONE_LABEL, type ZoneId } from './layout'

/**
 * 등각(아이소메트릭) 사무실 한 층. 평면은 깊이 x 0~400, 길이 y 0~900이고 길이 축이 화면 왼쪽 위에서 오른쪽 아래로 놓인다.
 * 업무 흐름 순서(회의실 → 구현 → 검증·보안 → 출시)대로 길이 축을 따라 구역을 둔다. 상태를 지어내지 않고 스냅샷·공개 사건만 보인다.
 */
export const FLOOR_W = 960
export const FLOOR_H = 580
export const PLATE_W = 400
export const PLATE_H = 900

const COS = 0.7071
const SIN = 0.3536

/** 평면 좌표 → 층 상자(FLOOR_W×FLOOR_H) 좌표. 평면 중심이 (480, 310)에 온다 */
export function project(px: number, py: number): { x: number; y: number } {
  const a = px - PLATE_W / 2
  const b = py - PLATE_H / 2
  return { x: Math.round(480 + COS * (a + b)), y: Math.round(310 + SIN * (b - a)) }
}

/** 평면의 길이 축(y) 거리 → 뒤쪽 긴 벽 위의 가로 위치 */
export const alongWall = (len: number) => Math.round(COS * len)

export interface IsoZone { id: ZoneId; label: string; x: number; y: number; w: number; h: number; tone: string }

export const ISO_ZONES: IsoZone[] = [
  { id: 'meeting', label: ZONE_LABEL.meeting, x: 0, y: 0, w: 400, h: 220, tone: 'var(--iso-meeting)' },
  { id: 'build', label: ZONE_LABEL.build, x: 0, y: 220, w: 400, h: 340, tone: 'var(--iso-build)' },
  { id: 'validate', label: ZONE_LABEL.validate, x: 210, y: 560, w: 190, h: 160, tone: 'var(--iso-validate)' },
  { id: 'security', label: ZONE_LABEL.security, x: 0, y: 560, w: 200, h: 160, tone: 'var(--iso-security)' },
  { id: 'release', label: ZONE_LABEL.release, x: 0, y: 720, w: 400, h: 180, tone: 'var(--iso-release)' },
]

/** 가구는 윗면 색과 옆면 색(CSS 변수 이름 접두)으로 그린다. cls는 높이 단계 */
export type Solid = 'e8' | 'e12' | 'e20' | 'e30' | 'e44' | 'e56' | 'part'
export interface Item { cls: Solid; x: number; y: number; w: number; h: number; paint: string; round?: boolean }

const DESK_W = 48
const DESK_H = 72
/** 책상 자리: 책상·모니터·의자. 사람은 의자 위치에 선다 */
const deskAt = (x: number, y: number): Item[] => [
  { cls: 'e12', x, y, w: DESK_W, h: DESK_H, paint: 'wood' },
  { cls: 'e30', x: x + 40, y: y + 22, w: 4, h: 28, paint: 'mon' },
  { cls: 'e8', x: x - 16, y: y + 28, w: 14, h: 16, paint: 'chair' },
]
const chairOf = (x: number, y: number) => ({ px: x - 9, py: y + 36 })

const DESKS: Record<Exclude<ZoneId, 'meeting'>, Array<[number, number]>> = {
  // 앉는 순서: 구역 안에 고르게 흩어지도록(이름표가 겹치지 않게) 화면 가로로 멀리 떨어진 자리부터 채운다
  build: [[60, 250], [280, 430], [170, 340], [60, 430], [280, 250], [170, 430], [60, 340], [280, 340], [170, 250]],
  validate: [[250, 590], [330, 590]],
  security: [[50, 590], [130, 590]],
  release: [[60, 760], [160, 760]],
}
/** 회의실은 책상 없이 탁자 둘레 의자에 선다 */
const MEETING_SPOTS = [{ px: 207, py: 82 }, { px: 207, py: 132 }, { px: 338, py: 82 }, { px: 338, py: 132 }, { px: 272, py: 196 }]

const SLOTS: Record<ZoneId, Array<{ px: number; py: number }>> = {
  meeting: MEETING_SPOTS,
  build: DESKS.build.map(([x, y]) => chairOf(x, y)),
  validate: DESKS.validate.map(([x, y]) => chairOf(x, y)),
  security: DESKS.security.map(([x, y]) => chairOf(x, y)),
  release: DESKS.release.map(([x, y]) => chairOf(x, y)),
}

const chair = (x: number, y: number): Item => ({ cls: 'e8', x, y, w: 14, h: 16, paint: 'chair' })

const DECOR: Item[] = [
  // 회의실: 의자를 두른 탁자
  { cls: 'e12', x: 222, y: 56, w: 96, h: 120, paint: 'table' },
  chair(204, 74), chair(204, 124), chair(326, 74), chair(326, 124),
  // 라운지: 소파·안락의자·원형 탁자
  { cls: 'e12', x: 118, y: 36, w: 34, h: 124, paint: 'sofa' },
  { cls: 'e20', x: 150, y: 36, w: 10, h: 124, paint: 'sofa' },
  { cls: 'e12', x: 28, y: 56, w: 30, h: 30, paint: 'sofa' },
  { cls: 'e12', x: 28, y: 122, w: 30, h: 30, paint: 'sofa' },
  { cls: 'e8', x: 72, y: 86, w: 32, h: 32, paint: 'wood', round: true },
  // 구현 구역: 뒤쪽 벽 책장
  { cls: 'e44', x: 372, y: 236, w: 22, h: 96, paint: 'shelf' },
  { cls: 'e44', x: 372, y: 448, w: 22, h: 96, paint: 'shelf' },
  // 보안실 잠금 보관함, 출시 게이트 랙
  { cls: 'e30', x: 150, y: 670, w: 40, h: 36, paint: 'file' },
  { cls: 'e56', x: 320, y: 740, w: 36, h: 52, paint: 'rack' },
  { cls: 'e56', x: 320, y: 820, w: 36, h: 52, paint: 'rack' },
  { cls: 'e56', x: 270, y: 820, w: 36, h: 52, paint: 'rack' },
  { cls: 'part', x: 0, y: 218, w: 160, h: 3, paint: 'glass' },
  { cls: 'part', x: 240, y: 218, w: 160, h: 3, paint: 'glass' },
  { cls: 'part', x: 0, y: 558, w: 160, h: 3, paint: 'glass' },
  { cls: 'part', x: 240, y: 558, w: 160, h: 3, paint: 'glass' },
  { cls: 'part', x: 203, y: 568, w: 3, h: 146, paint: 'glass' },
  { cls: 'part', x: 0, y: 718, w: 160, h: 3, paint: 'glass' },
  { cls: 'part', x: 240, y: 718, w: 160, h: 3, paint: 'glass' },
]

/** 바닥에 깔린 러그(입체 없음) */
export const RUGS: Array<{ x: number; y: number; w: number; h: number; paint: string; round: boolean }> = [
  { x: 14, y: 24, w: 160, h: 156, paint: 'rug-1', round: true },
  { x: 196, y: 40, w: 150, h: 156, paint: 'rug-2', round: false },
  { x: 30, y: 236, w: 330, h: 300, paint: 'rug-3', round: false },
  { x: 222, y: 574, w: 166, h: 132, paint: 'rug-4', round: false },
  { x: 12, y: 574, w: 176, h: 132, paint: 'rug-5', round: false },
]

/** 바닥 위 입체물 전부(책상 자리는 빈자리도 그린다). 뒤쪽부터 그리도록 깊이로 정렬 */
export const FLOOR_ITEMS: Item[] = [...DECOR, ...Object.values(DESKS).flatMap((list) => list.flatMap(([x, y]) => deskAt(x, y)))]
  .map((it) => ({ it, k: it.y + it.h / 2 - (it.x + it.w / 2) }))
  .sort((p, q) => p.k - q.k)
  .map(({ it }) => it)

export const PLANTS: Array<[number, number]> = [[388, 14], [388, 214], [388, 556], [388, 890], [14, 14], [186, 214], [14, 560], [200, 890]]
/** 뒤쪽 긴 벽의 창·화이트보드: [길이 축 시작, 길이, 종류] */
export const WALL_PANES: Array<[number, number, 'win' | 'whiteboard']> = [[24, 180, 'whiteboard'], [250, 90, 'win'], [370, 90, 'win'], [490, 90, 'win'], [610, 90, 'win'], [740, 140, 'win']]
export const SHORT_PANES: Array<[number, number]> = [[30, 130]]
/** 짧은 뒤쪽 벽의 엘리베이터 문: [깊이 축 시작, 너비] */
export const ELEVATOR_AT: [number, number] = [196, 130]

export interface IsoSeat { taskId: string; zone: ZoneId; px: number; py: number }

/** 작업을 역할 구역 자리에 앉힌다. 대체된 작업은 놓지 않고, 자리가 모자라면 넘친 수를 남긴다(DOM 목록에는 모두 있다) */
export function placeSeats(tasks: readonly Task[]): { seats: IsoSeat[]; overflow: Partial<Record<ZoneId, number>> } {
  const seats: IsoSeat[] = []
  const overflow: Partial<Record<ZoneId, number>> = {}
  for (const zone of ISO_ZONES) {
    const here = tasks.filter((t) => t.state !== 'superseded' && ROLE_ZONE[t.role] === zone.id)
    const slots = SLOTS[zone.id]
    here.slice(0, slots.length).forEach((t, i) => seats.push({ taskId: t.id, zone: zone.id, ...slots[i] }))
    if (here.length > slots.length) overflow[zone.id] = here.length - slots.length
  }
  return { seats, overflow }
}

export type BubbleTone = 'active' | 'ok' | 'danger' | 'neutral'

/** 스냅샷 상태의 말풍선. 대기·착수 가능은 흐린 사람으로만 보인다 */
export function bubbleFor(task: Task): { text: string; tone: BubbleTone } | null {
  switch (task.state) {
    case 'running': return { text: '작업 중', tone: 'active' }
    case 'succeeded': return { text: '완료', tone: 'ok' }
    case 'failed': return { text: '실패', tone: 'danger' }
    case 'blocked': return { text: '막힘', tone: 'danger' }
    case 'cancelled': return { text: '취소', tone: 'neutral' }
    default: return null
  }
}

/** 방금 받은 공개 사건을 잠깐 보이는 말풍선 문구로. 성공·실패 판정은 스냅샷 상태에 맡긴다 */
export function flashFor(event: RunEvent): string | null {
  if (!event.task_id) return null
  switch (event.event_type) {
    case 'task_finished': return '방금 끝남'
    case 'review_submitted': return '보고서 제출'
    case 'tool_finished':
    case 'retrieval_finished':
    case 'context_saved': return '근거 저장'
    case 'warning':
    case 'operation_uncertain': return '확인 필요'
    default: return null
  }
}
