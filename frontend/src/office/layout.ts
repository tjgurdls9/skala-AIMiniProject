import type { Role, Task } from '../api/types'

/** 업무 흐름 순서: 명세 회의실 → 구현 구역 → 분리된 검증실·보안실 → 출시 게이트 */
export type ZoneId = 'meeting' | 'build' | 'validate' | 'security' | 'release'

export interface Rect { x: number; y: number; w: number; h: number }
export interface Zone extends Rect { id: ZoneId; label: string }
export interface Seat { taskId: string; zone: ZoneId; x: number; y: number; w: number; h: number }
export interface OfficeLayout { width: number; height: number; zones: Zone[]; seats: Seat[]; compact: boolean }

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

const COMPACT_BELOW = 560
const PAD = 10
const LABEL_H = 26
const SEAT_W = 64
const SEAT_H = 66

/** 넓은 화면은 한 줄 흐름, 좁은 화면은 두 줄(위: 회의실·구현 / 아래: 검증·보안·출시) */
export function zoneRects(width: number, height: number): { zones: Zone[]; compact: boolean } {
  const compact = width < COMPACT_BELOW
  const z = (id: ZoneId, x: number, y: number, w: number, h: number): Zone => ({ id, label: ZONE_LABEL[id], x, y, w, h })
  if (compact) {
    const topH = Math.round(height * 0.55)
    const botH = height - topH
    const meetW = Math.round(width * 0.36)
    const third = width / 3
    return {
      compact,
      zones: [
        z('meeting', 0, 0, meetW, topH),
        z('build', meetW, 0, width - meetW, topH),
        z('validate', 0, topH, third, botH),
        z('security', third, topH, third, botH),
        z('release', third * 2, topH, width - third * 2, botH),
      ],
    }
  }
  const unit = width / 10
  const half = height / 2
  return {
    compact,
    zones: [
      z('meeting', 0, 0, unit * 2, height),
      z('build', unit * 2, 0, unit * 4.4, height),
      z('validate', unit * 6.4, 0, unit * 1.9, half),
      z('security', unit * 6.4, half, unit * 1.9, height - half),
      z('release', unit * 8.3, 0, width - unit * 8.3, height),
    ],
  }
}

const MAX_SCALE = 1.7
const MIN_SCALE = 0.45

/** 가장 큰 배율부터 줄여 가며 구역 안에 겹치지 않게 들어가는 격자를 찾는다. */
export function fitGrid(count: number, innerW: number, innerH: number): { cols: number; scale: number } {
  for (let scale = MAX_SCALE; scale > MIN_SCALE; scale -= 0.05) {
    const cols = Math.max(1, Math.floor(innerW / (SEAT_W * scale)))
    if (Math.ceil(count / cols) * SEAT_H * scale <= innerH) return { cols, scale }
  }
  return { cols: Math.max(1, Math.floor(innerW / (SEAT_W * MIN_SCALE))), scale: MIN_SCALE }
}

/** 구역 안에 좌석을 격자로, 가운데 정렬해 배치한다. */
function placeSeats(zone: Zone, tasks: readonly Task[]): Seat[] {
  if (tasks.length === 0) return []
  const innerW = zone.w - PAD * 2
  const innerH = zone.h - LABEL_H - PAD * 2
  const { cols, scale } = fitGrid(tasks.length, innerW, innerH)
  const w = SEAT_W * scale
  const h = SEAT_H * scale
  const rows = Math.ceil(tasks.length / cols)
  const usedCols = Math.min(cols, tasks.length)
  const offsetX = zone.x + PAD + (innerW - usedCols * w) / 2
  const offsetY = zone.y + LABEL_H + PAD + Math.max(0, (innerH - rows * h) / 2)
  return tasks.map((t, i) => ({
    taskId: t.id,
    zone: zone.id,
    x: offsetX + (i % cols) * w,
    y: offsetY + Math.floor(i / cols) * h,
    w,
    h,
  }))
}

export function computeLayout(width: number, height: number, tasks: readonly Task[]): OfficeLayout {
  const { zones, compact } = zoneRects(width, height)
  const visible = tasks.filter((t) => t.state !== 'superseded')
  const seats = zones.flatMap((zone) => placeSeats(zone, visible.filter((t) => ROLE_ZONE[t.role] === zone.id)))
  return { width, height, zones, seats, compact }
}

export function hitSeat(layout: OfficeLayout, x: number, y: number): string | null {
  const seat = layout.seats.find((s) => x >= s.x && x <= s.x + s.w && y >= s.y && y <= s.y + s.h)
  return seat?.taskId ?? null
}

export function zoneCenter(layout: OfficeLayout, id: ZoneId): { x: number; y: number } {
  const zone = layout.zones.find((z) => z.id === id)
  return zone ? { x: zone.x + zone.w / 2, y: zone.y + LABEL_H / 2 + 4 } : { x: 0, y: 0 }
}
