import type { Role, Task } from '../api/types'

/** 업무 흐름 순서: 명세 회의실 → 구현 구역 → 분리된 검증실·보안실 → 출시 게이트 */
export type ZoneId = 'meeting' | 'build' | 'validate' | 'security' | 'release'

export interface Rect { x: number; y: number; w: number; h: number }
/** 타일 단위 방(벽 안쪽) */
export interface Room extends Rect { id: ZoneId; label: string }
export interface Zone extends Rect { id: ZoneId; label: string }
/** 좌석: tx/ty는 타일 좌표(지도), x/y/w/h는 화면 좌표(클릭·라벨) */
export interface Seat extends Rect { taskId: string; zone: ZoneId; tx: number; ty: number }
export interface Door { x: number; y: number; vertical: boolean; length: number }
export interface TileMap { w: number; h: number; rooms: Room[]; doors: Door[] }

export interface OfficeLayout {
  width: number
  height: number
  compact: boolean
  map: TileMap
  /** 지도 1px → 화면 px 배율과 화면상의 지도 시작점 */
  scale: number
  ox: number
  oy: number
  zones: Zone[]
  seats: Seat[]
  /** 방 크기를 넘어 장면에 못 놓은 작업 수(DOM 목록에는 모두 있음) */
  overflow: Partial<Record<ZoneId, number>>
}

export const TILE = 16
/** 좌석 한 칸: 사람(2타일) + 책상(1타일), 가로 3타일 */
const CELL_W = 3
const CELL_H = 3

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

const room = (id: ZoneId, x: number, y: number, w: number, h: number): Room => ({ id, label: ZONE_LABEL[id], x, y, w, h })

/** 가로 화면: 한 줄 흐름. 검증실과 보안실은 벽으로 분리한다 */
const WIDE: TileMap = {
  w: 40,
  h: 22,
  rooms: [room('meeting', 1, 1, 9, 20), room('build', 11, 1, 15, 20), room('validate', 27, 1, 7, 9), room('security', 27, 11, 7, 10), room('release', 35, 1, 4, 20)],
  doors: [
    { x: 10, y: 9, vertical: true, length: 3 },
    { x: 26, y: 4, vertical: true, length: 2 },
    { x: 26, y: 15, vertical: true, length: 2 },
    { x: 34, y: 4, vertical: true, length: 2 },
    { x: 34, y: 15, vertical: true, length: 2 },
  ],
}

/** 세로·좁은 화면: 위(회의실·구현) / 아래(검증·보안·출시) */
const TALL: TileMap = {
  w: 22,
  h: 30,
  rooms: [room('meeting', 1, 1, 8, 13), room('build', 10, 1, 11, 13), room('validate', 1, 15, 6, 14), room('security', 8, 15, 6, 14), room('release', 15, 15, 6, 14)],
  doors: [
    { x: 9, y: 6, vertical: true, length: 2 },
    { x: 3, y: 14, vertical: false, length: 2 },
    { x: 10, y: 14, vertical: false, length: 2 },
    { x: 17, y: 14, vertical: false, length: 2 },
  ],
}

const COMPACT_ASPECT = 1.15
/** 지도 둘레에 배경이 보이도록 남기는 여백 비율 */
const FIT_MARGIN = 0.94

export function chooseMap(width: number, height: number): { map: TileMap; compact: boolean } {
  const compact = height > 0 && width / height < COMPACT_ASPECT
  return { map: compact ? TALL : WIDE, compact }
}

/**
 * 지도를 화면에 맞춘다. 3배 이상이면 정수 배율로 내려 픽셀을 선명하게 하고(화면이 조금 작아져도 선명도 우선),
 * 1~3배는 0.25 단위, 그보다 작으면 그대로 줄인다. 남는 공간은 배경 연출로 채운다.
 */
export function fitMap(map: TileMap, width: number, height: number): { scale: number; ox: number; oy: number } {
  const raw = Math.min(width / (map.w * TILE), height / (map.h * TILE)) * FIT_MARGIN
  const scale = raw >= 3 ? Math.floor(raw) : raw >= 1 ? Math.floor(raw * 4) / 4 : Math.max(raw, 0.01)
  return { scale, ox: Math.round((width - map.w * TILE * scale) / 2), oy: Math.round((height - map.h * TILE * scale) / 2) }
}

/** 방 위쪽 2타일은 벽면(3/4 시점), 그 아래 여유 */
export const WALL_FACE_ROWS = 2
const SIGN_ROWS = 2.5
const FURNITURE_SHARE = 0.25
const FURNITURE_MIN_ROOM_H = 10

export function seatSlots(r: Room): Array<{ tx: number; ty: number }> {
  const reserve = r.h >= FURNITURE_MIN_ROOM_H ? Math.floor(r.h * FURNITURE_SHARE) : 0
  const cols = Math.max(1, Math.floor(r.w / CELL_W))
  const rows = Math.max(1, Math.floor((r.h - SIGN_ROWS - reserve) / CELL_H))
  const offX = r.x + Math.floor((r.w - cols * CELL_W) / 2)
  const slots: Array<{ tx: number; ty: number }> = []
  for (let row = 0; row < rows; row++) {
    for (let col = 0; col < cols; col++) slots.push({ tx: offX + col * CELL_W, ty: r.y + SIGN_ROWS + row * CELL_H })
  }
  return slots
}

export function computeLayout(width: number, height: number, tasks: readonly Task[]): OfficeLayout {
  const { map, compact } = chooseMap(width, height)
  const { scale, ox, oy } = fitMap(map, width, height)
  const px = TILE * scale
  const toScreen = (r: Rect): Rect => ({ x: ox + r.x * px, y: oy + r.y * px, w: r.w * px, h: r.h * px })
  const visible = tasks.filter((t) => t.state !== 'superseded')
  const seats: Seat[] = []
  const overflow: Partial<Record<ZoneId, number>> = {}
  for (const r of map.rooms) {
    const here = visible.filter((t) => ROLE_ZONE[t.role] === r.id)
    const slots = seatSlots(r)
    const fits = here.length <= slots.length ? here : here.slice(0, slots.length - 1)
    if (fits.length < here.length) overflow[r.id] = here.length - fits.length
    fits.forEach((t, i) => {
      const { tx, ty } = slots[i]
      seats.push({ taskId: t.id, zone: r.id, tx, ty, ...toScreen({ x: tx, y: ty, w: CELL_W, h: CELL_H }) })
    })
  }
  const zones = map.rooms.map((r) => ({ id: r.id, label: r.label, ...toScreen(r) }))
  return { width, height, compact, map, scale, ox, oy, zones, seats, overflow }
}

export function hitSeat(layout: OfficeLayout, x: number, y: number): string | null {
  const seat = layout.seats.find((s) => x >= s.x && x <= s.x + s.w && y >= s.y && y <= s.y + s.h)
  return seat?.taskId ?? null
}

/** 방 표지판 위치(지도 좌표, 픽셀) — 근거 패킷이 향하는 곳 */
export function zoneCenter(layout: OfficeLayout, id: ZoneId): { x: number; y: number } {
  const r = layout.map.rooms.find((z) => z.id === id)
  return r ? { x: (r.x + r.w / 2) * TILE, y: (r.y + WALL_FACE_ROWS) * TILE } : { x: 0, y: 0 }
}
