import type { Role, RunEvent, Task } from '../api/types'
import { TASK_STATE, type Tone } from '../model/labels'
import { ROLE_ZONE, TILE, zoneCenter, type OfficeLayout, type Room, type Seat, type TileMap } from './layout'

/** 수신한 공개 사건에 대한 연출만. 아직 일어나지 않은 성공을 그리지 않는다. 좌표는 지도 픽셀. */
export interface Packet {
  from: { x: number; y: number }
  to: { x: number; y: number }
  startedAt: number
  kind: 'evidence' | 'report' | 'done' | 'alert'
}

export const PACKET_MS = 900

type Palette = Record<string, string>

const PALETTE_NAMES = [
  'px-void', 'px-wall', 'px-wall-top', 'px-wood', 'px-wood-2', 'px-carpet', 'px-carpet-2', 'px-tile', 'px-tile-2',
  'px-tile-v', 'px-tile-s', 'px-concrete', 'px-concrete-2', 'px-desk', 'px-desk-edge', 'px-monitor', 'px-screen',
  'px-plant', 'px-plant-2', 'px-label-bg', 'px-label-ink', 'px-shadow',
  'ink', 'surface', 'focus',
  'role-planner', 'role-supervisor', 'role-builder', 'role-validator', 'role-security', 'role-release',
  'tone-neutral', 'tone-active', 'tone-ok', 'tone-warn', 'tone-danger', 'tone-wait',
]

export function readPalette(el: Element): Palette {
  const style = getComputedStyle(el)
  return Object.fromEntries(PALETTE_NAMES.map((n) => [n, style.getPropertyValue(`--${n}`).trim() || '#888']))
}

const roleColor = (p: Palette, role: Role) => p[`role-${role}`]
const toneColor = (p: Palette, tone: Tone) => p[`tone-${tone}`]

/** 사람마다 다른 머리·피부색(작업 ID 해시). 상태와 무관한 외형이다 */
const SKIN = ['#f1c7a3', '#d9a07a', '#a8714f', '#7a4e33']
const HAIR = ['#2b2420', '#5a3a22', '#8a5a2b', '#c9a15b', '#3c3f52', '#6b2f2f']
function hash(text: string): number {
  let h = 0
  for (let i = 0; i < text.length; i++) h = (h * 31 + text.charCodeAt(i)) | 0
  return Math.abs(h)
}

// ── 정적 층: 바닥·벽·가구 (지도 해상도) ──────────────────────────────

function fillChecker(ctx: CanvasRenderingContext2D, r: Room, a: string, b: string, size: number) {
  const x0 = r.x * TILE
  const y0 = r.y * TILE
  ctx.fillStyle = a
  ctx.fillRect(x0, y0, r.w * TILE, r.h * TILE)
  ctx.fillStyle = b
  for (let y = 0; y < r.h * TILE; y += size) {
    for (let x = (y / size) % 2 ? size : 0; x < r.w * TILE; x += size * 2) ctx.fillRect(x0 + x, y0 + y, size, size)
  }
}

function fillPlanks(ctx: CanvasRenderingContext2D, r: Room, a: string, b: string) {
  const x0 = r.x * TILE
  const y0 = r.y * TILE
  ctx.fillStyle = a
  ctx.fillRect(x0, y0, r.w * TILE, r.h * TILE)
  ctx.fillStyle = b
  for (let y = 0; y < r.h * TILE; y += 4) {
    ctx.fillRect(x0, y0 + y + 3, r.w * TILE, 1)
    const offset = (y / 4) % 2 ? 10 : 26
    for (let x = offset; x < r.w * TILE; x += 32) ctx.fillRect(x0 + x, y0 + y, 1, 3)
  }
}

function floor(ctx: CanvasRenderingContext2D, r: Room, p: Palette) {
  if (r.id === 'meeting') {
    fillChecker(ctx, r, p['px-carpet'], p['px-carpet-2'], 4)
  } else if (r.id === 'build') {
    fillPlanks(ctx, r, p['px-wood'], p['px-wood-2'])
  } else if (r.id === 'validate') {
    fillChecker(ctx, r, p['px-tile'], p['px-tile-v'], 8)
  } else if (r.id === 'security') {
    fillChecker(ctx, r, p['px-tile'], p['px-tile-s'], 8)
  } else {
    fillChecker(ctx, r, p['px-concrete'], p['px-concrete-2'], 16)
  }
}

function walls(ctx: CanvasRenderingContext2D, map: TileMap, p: Palette) {
  // 방 바깥은 모두 벽, 방·문은 바닥으로 다시 칠한다
  ctx.fillStyle = p['px-wall']
  ctx.fillRect(0, 0, map.w * TILE, map.h * TILE)
  map.rooms.forEach((r) => floor(ctx, r, p))
  for (const d of map.doors) {
    ctx.fillStyle = p['px-concrete']
    if (d.vertical) ctx.fillRect(d.x * TILE, d.y * TILE, TILE, d.length * TILE)
    else ctx.fillRect(d.x * TILE, d.y * TILE, d.length * TILE, TILE)
  }
  // 벽 윗면 하이라이트(방 위쪽 경계)
  ctx.fillStyle = p['px-wall-top']
  for (const r of map.rooms) ctx.fillRect(r.x * TILE, r.y * TILE - 4, r.w * TILE, 4)
  // 방 안쪽 그림자
  ctx.fillStyle = p['px-shadow']
  for (const r of map.rooms) ctx.fillRect(r.x * TILE, r.y * TILE, r.w * TILE, 3)
}

function plant(ctx: CanvasRenderingContext2D, x: number, y: number, p: Palette) {
  ctx.fillStyle = p['px-desk-edge']
  ctx.fillRect(x + 4, y + 10, 8, 6)
  ctx.fillStyle = p['px-plant']
  ctx.fillRect(x + 2, y + 2, 12, 9)
  ctx.fillStyle = p['px-plant-2']
  ctx.fillRect(x + 5, y, 6, 4)
  ctx.fillRect(x + 3, y + 5, 3, 3)
  ctx.fillRect(x + 10, y + 6, 3, 3)
}

function furniture(ctx: CanvasRenderingContext2D, r: Room, p: Palette) {
  const x0 = r.x * TILE
  const y0 = r.y * TILE
  const right = (r.x + r.w) * TILE
  const bottom = (r.y + r.h) * TILE
  plant(ctx, right - TILE, y0 + 2, p)
  if (r.id === 'meeting') {
    // 명세 화이트보드 + 회의 탁자
    const bw = Math.min(r.w * TILE - 70, 56)
    const bx = right - TILE - 6 - bw
    ctx.fillStyle = '#f2f1ea'
    ctx.fillRect(bx, y0 + 3, bw, 10)
    ctx.fillStyle = p['role-planner']
    ctx.fillRect(bx + 4, y0 + 6, bw * 0.4, 1)
    ctx.fillRect(bx + 4, y0 + 9, bw * 0.6, 1)
    const tw = Math.min(r.w * TILE - 24, 96)
    ctx.fillStyle = p['px-desk-edge']
    ctx.fillRect(x0 + (r.w * TILE - tw) / 2, bottom - 44, tw, 26)
    ctx.fillStyle = p['px-desk']
    ctx.fillRect(x0 + (r.w * TILE - tw) / 2 + 2, bottom - 44, tw - 4, 22)
    plant(ctx, x0 + 2, bottom - TILE - 2, p)
  } else if (r.id === 'build') {
    // 책장 + 러그
    ctx.fillStyle = p['px-desk-edge']
    ctx.fillRect(x0 + 4, bottom - 34, 40, 30)
    ctx.fillStyle = p['role-builder']
    for (let i = 0; i < 6; i++) ctx.fillRect(x0 + 8 + i * 6, bottom - 30, 4, 10)
    ctx.fillStyle = p['role-planner']
    for (let i = 0; i < 5; i++) ctx.fillRect(x0 + 8 + i * 7, bottom - 17, 5, 9)
    plant(ctx, right - TILE, bottom - TILE - 2, p)
  } else if (r.id === 'security') {
    // 서버 랙
    ctx.fillStyle = p['px-monitor']
    ctx.fillRect(x0 + 4, bottom - 40, 18, 36)
    ctx.fillStyle = p['role-security']
    for (let i = 0; i < 5; i++) ctx.fillRect(x0 + 7, bottom - 36 + i * 7, 2, 2)
  } else if (r.id === 'validate') {
    // 검사 체크보드
    ctx.fillStyle = '#f2f1ea'
    ctx.fillRect(x0 + 4, bottom - 18, 22, 12)
    ctx.fillStyle = p['role-validator']
    for (let i = 0; i < 3; i++) ctx.fillRect(x0 + 7, bottom - 16 + i * 3, 14, 1)
  } else if (r.id === 'release') {
    // 출시 게이트 아치 + 경고 줄무늬
    const gx = x0 + (r.w * TILE) / 2 - 22
    const gy = bottom - 70
    ctx.fillStyle = p['px-desk-edge']
    ctx.fillRect(gx, gy, 6, 60)
    ctx.fillRect(gx + 38, gy, 6, 60)
    ctx.fillRect(gx, gy, 44, 6)
    ctx.fillStyle = p['role-release']
    ctx.fillRect(gx + 6, gy + 6, 32, 2)
    for (let i = 0; i < 6; i++) {
      ctx.fillStyle = i % 2 ? p['tone-warn'] : p['px-monitor']
      ctx.fillRect(gx + 6 + i * 6, bottom - 8, 6, 4)
    }
  }
}

export function drawStatic(ctx: CanvasRenderingContext2D, map: TileMap, p: Palette): void {
  walls(ctx, map, p)
  map.rooms.forEach((r) => furniture(ctx, r, p))
}

let staticCache: { key: string; canvas: HTMLCanvasElement } | null = null

/** 정적 층을 한 번만 그려 둔다. 캔버스를 만들 수 없으면 null(직접 그리기로 대체) */
function staticLayer(map: TileMap, p: Palette): HTMLCanvasElement | null {
  const key = `${map.w}x${map.h}|${PALETTE_NAMES.map((n) => p[n]).join(',')}`
  if (staticCache?.key === key) return staticCache.canvas
  const canvas = document.createElement('canvas')
  canvas.width = map.w * TILE
  canvas.height = map.h * TILE
  const ctx = canvas.getContext('2d')
  if (!ctx) return null
  drawStatic(ctx, map, p)
  staticCache = { key, canvas }
  return canvas
}

// ── 동적 층: 책상·사람·말풍선·패킷 (지도 좌표) ───────────────────────

function desk(ctx: CanvasRenderingContext2D, seat: Seat, task: Task, p: Palette) {
  const x = seat.tx * TILE
  const y = seat.ty * TILE
  ctx.fillStyle = p['px-shadow']
  ctx.fillRect(x + 4, y + 41, 40, 3)
  ctx.fillStyle = p['px-desk-edge']
  ctx.fillRect(x + 3, y + 30, 42, 11)
  ctx.fillStyle = p['px-desk']
  ctx.fillRect(x + 3, y + 28, 42, 9)
  // 모니터 뒷면 + 실행 중일 때만 화면 빛
  ctx.fillStyle = p['px-monitor']
  ctx.fillRect(x + 17, y + 22, 14, 9)
  ctx.fillRect(x + 22, y + 31, 4, 2)
  if (task.state === 'running') {
    ctx.fillStyle = p['px-screen']
    ctx.fillRect(x + 15, y + 20, 18, 2)
  }
}

function person(ctx: CanvasRenderingContext2D, seat: Seat, task: Task, p: Palette, frame: number) {
  const x = seat.tx * TILE + 17
  const y = seat.ty * TILE + 4
  const h = hash(task.id)
  const dim = task.state === 'cancelled'
  ctx.globalAlpha = dim ? 0.45 : 1
  // 몸통(역할 색) + 팔
  ctx.fillStyle = roleColor(p, task.role)
  ctx.fillRect(x + 1, y + 13, 12, 9)
  ctx.fillStyle = SKIN[h % SKIN.length]
  const typing = task.state === 'running'
  const lift = typing && frame % 2 === 1 ? 1 : 0
  ctx.fillRect(x - 1, y + 15 + lift, 2, 6)
  ctx.fillRect(x + 13, y + 15 + (typing && frame % 2 === 0 ? 1 : 0), 2, 6)
  // 얼굴·머리
  ctx.fillRect(x + 2, y + 3, 10, 9)
  ctx.fillStyle = HAIR[h % HAIR.length]
  ctx.fillRect(x + 1, y, 12, 4)
  ctx.fillRect(x + 1, y + 3, 2, 4)
  ctx.fillRect(x + 11, y + 3, 2, 4)
  ctx.fillStyle = '#2b2420'
  ctx.fillRect(x + 4, y + 7, 2, 2)
  ctx.fillRect(x + 8, y + 7, 2, 2)
  ctx.globalAlpha = 1
}

function packet(ctx: CanvasRenderingContext2D, pk: Packet, now: number, p: Palette) {
  const t = Math.min(1, (now - pk.startedAt) / PACKET_MS)
  const ease = 1 - (1 - t) ** 3
  const x = pk.from.x + (pk.to.x - pk.from.x) * ease
  const y = pk.from.y + (pk.to.y - pk.from.y) * ease - Math.sin(Math.PI * t) * 14
  const color = pk.kind === 'alert' ? toneColor(p, 'danger') : pk.kind === 'done' ? toneColor(p, 'ok') : toneColor(p, 'active')
  ctx.fillStyle = '#ffffff'
  ctx.fillRect(x - 4, y - 5, 8, 10)
  ctx.fillStyle = color
  ctx.fillRect(x - 4, y - 5, 8, 2)
  ctx.fillRect(x - 2, y - 1, 5, 1)
  ctx.fillRect(x - 2, y + 2, 4, 1)
}

// ── 화면 좌표 층: 말풍선·표지판·라벨(선명한 글자) ──────────────────────

/** 상태 표식. 실행 중은 손 움직임과 화면 빛으로 보여 주고 말풍선은 없다 */
const BUBBLE: Partial<Record<Task['state'], { glyph: string; tone: Tone }>> = {
  pending: { glyph: '…', tone: 'neutral' },
  blocked: { glyph: '!', tone: 'danger' },
  failed: { glyph: '✕', tone: 'danger' },
  succeeded: { glyph: '✓', tone: 'ok' },
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.arcTo(x + w, y, x + w, y + h, r)
  ctx.arcTo(x + w, y + h, x, y + h, r)
  ctx.arcTo(x, y + h, x, y, r)
  ctx.arcTo(x, y, x + w, y, r)
  ctx.closePath()
}

function truncate(ctx: CanvasRenderingContext2D, text: string, max: number): string {
  if (ctx.measureText(text).width <= max) return text
  let t = text
  while (t.length > 1 && ctx.measureText(`${t}…`).width > max) t = t.slice(0, -1)
  return `${t}…`
}

function seatOverlay(ctx: CanvasRenderingContext2D, seat: Seat, task: Task, p: Palette, selected: boolean, px: number) {
  const bubble = BUBBLE[task.state]
  const cx = seat.x + seat.w / 2
  if (bubble) {
    const size = Math.max(14, px * 0.75)
    const bx = cx + px * 0.35
    const by = seat.y - size * 0.15
    ctx.fillStyle = p.surface
    roundRect(ctx, bx, by, size, size, size * 0.3)
    ctx.fill()
    ctx.strokeStyle = toneColor(p, bubble.tone)
    ctx.lineWidth = Math.max(1.5, px * 0.08)
    ctx.stroke()
    ctx.fillStyle = toneColor(p, bubble.tone)
    ctx.font = `700 ${Math.round(size * 0.7)}px system-ui, sans-serif`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(bubble.glyph, bx + size / 2, by + size / 2 + 1)
  }
  if (selected) {
    ctx.strokeStyle = p.focus
    ctx.lineWidth = 3
    roundRect(ctx, seat.x + 2, seat.y + 2, seat.w - 4, seat.h - 4, 6)
    ctx.stroke()
  }
  // 이름표: 충분히 클 때만(작으면 DOM 목록이 같은 정보를 준다)
  if (px >= 18) {
    const state = TASK_STATE[task.state]
    const fontPx = Math.round(Math.min(13, Math.max(10, px * 0.42)))
    ctx.font = `600 ${fontPx}px system-ui, sans-serif`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'top'
    const label = truncate(ctx, task.title, seat.w - 10)
    const ly = seat.y + seat.h - 2
    const lw = Math.min(seat.w - 2, ctx.measureText(label).width + 10)
    ctx.fillStyle = p['px-label-bg']
    roundRect(ctx, cx - lw / 2, ly, lw, fontPx * 2.5, 4)
    ctx.fill()
    ctx.fillStyle = p['px-label-ink']
    ctx.fillText(label, cx, ly + 2)
    ctx.fillStyle = toneColor(p, state.tone)
    ctx.font = `700 ${fontPx - 1}px system-ui, sans-serif`
    ctx.fillText(`${state.glyph} ${state.text}`, cx, ly + fontPx + 4)
  }
}

function roomSigns(ctx: CanvasRenderingContext2D, layout: OfficeLayout, p: Palette, counts: Map<string, number>) {
  const fontPx = Math.round(Math.min(15, Math.max(11, TILE * layout.scale * 0.5)))
  ctx.font = `700 ${fontPx}px system-ui, sans-serif`
  ctx.textAlign = 'left'
  ctx.textBaseline = 'middle'
  for (const z of layout.zones) {
    const n = counts.get(z.id) ?? 0
    const more = layout.overflow[z.id] ? ` +${layout.overflow[z.id]}` : ''
    const text = n ? `${z.label} · ${n}${more}` : z.label
    const w = ctx.measureText(text).width + 14
    const h = fontPx + 10
    ctx.fillStyle = p['px-label-bg']
    roundRect(ctx, z.x + 6, z.y + 6, w, h, h / 2)
    ctx.fill()
    ctx.fillStyle = n ? p['px-label-ink'] : p['tone-neutral']
    ctx.fillText(text, z.x + 13, z.y + 6 + h / 2 + 0.5)
  }
}

export interface SceneState {
  layout: OfficeLayout
  tasks: ReadonlyMap<string, Task>
  selectedTaskId: string | null
  packets: readonly Packet[]
  frame: number
  now: number
}

/** dpr은 캔버스 픽셀 비율. 모든 좌표는 CSS 픽셀 기준으로 받는다 */
export function drawScene(ctx: CanvasRenderingContext2D, scene: SceneState, p: Palette, dpr = 1): void {
  const { layout } = scene
  const s = layout.scale
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.imageSmoothingEnabled = false
  ctx.fillStyle = p['px-void']
  ctx.fillRect(0, 0, layout.width, layout.height)

  // 지도 좌표로 전환
  ctx.setTransform(dpr * s, 0, 0, dpr * s, dpr * layout.ox, dpr * layout.oy)
  const layer = staticLayer(layout.map, p)
  if (layer) ctx.drawImage(layer, 0, 0)
  else drawStatic(ctx, layout.map, p)
  for (const seat of layout.seats) {
    const task = scene.tasks.get(seat.taskId)
    if (!task) continue
    person(ctx, seat, task, p, scene.frame)
    desk(ctx, seat, task, p)
  }
  scene.packets.forEach((pk) => packet(ctx, pk, scene.now, p))

  // 화면 좌표: 선명한 글자·말풍선
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  const counts = new Map<string, number>()
  scene.tasks.forEach((t) => {
    if (t.state !== 'superseded') counts.set(ROLE_ZONE[t.role], (counts.get(ROLE_ZONE[t.role]) ?? 0) + 1)
  })
  roomSigns(ctx, layout, p, counts)
  for (const seat of layout.seats) {
    const task = scene.tasks.get(seat.taskId)
    if (task) seatOverlay(ctx, seat, task, p, task.id === scene.selectedTaskId, TILE * s)
  }
  ctx.textAlign = 'start'
}

/** 사건을 장면 연출로 바꾼다. 장면에 없는 작업·근거 없는 사건은 연출하지 않는다. */
export function packetFor(event: RunEvent, layout: OfficeLayout, tasks: ReadonlyMap<string, Task>, now: number): Packet | null {
  const task = event.task_id ? tasks.get(event.task_id) : undefined
  const seat = task ? layout.seats.find((st) => st.taskId === task.id) : undefined
  if (!task || !seat) return null
  const from = { x: seat.tx * TILE + 24, y: seat.ty * TILE + 18 }
  const zone = ROLE_ZONE[task.role]
  switch (event.event_type) {
    case 'tool_finished':
    case 'retrieval_finished':
    case 'context_saved':
      return { from, to: zoneCenter(layout, zone), startedAt: now, kind: 'evidence' }
    case 'review_submitted':
      return { from, to: zoneCenter(layout, 'release'), startedAt: now, kind: 'report' }
    case 'task_finished':
      // 성공/실패 색은 스냅샷 상태가 확인된 경우에만 쓴다
      return { from, to: { x: from.x, y: from.y - 24 }, startedAt: now, kind: task.state === 'failed' ? 'alert' : task.state === 'succeeded' ? 'done' : 'evidence' }
    case 'warning':
    case 'operation_uncertain':
      return { from, to: { x: from.x, y: from.y - 24 }, startedAt: now, kind: 'alert' }
    default:
      return null
  }
}
