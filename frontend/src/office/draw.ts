import type { Role, RunEvent, Task } from '../api/types'
import { TASK_STATE, type Tone } from '../model/labels'
import { box, cast, drawStatic, seeded, type Palette } from './art'
import { ROLE_ZONE, TILE, WALL_FACE_ROWS, zoneCenter, type OfficeLayout, type Seat, type TileMap } from './layout'

export { drawStatic }

/** 수신한 공개 사건에 대한 연출만. 아직 일어나지 않은 성공을 그리지 않는다. 좌표는 지도 픽셀. */
export interface Packet {
  from: { x: number; y: number }
  to: { x: number; y: number }
  startedAt: number
  kind: 'evidence' | 'report' | 'done' | 'alert'
}

export const PACKET_MS = 900
/** 첫 진입 때 방마다 불이 켜지는 장식 인트로(상태와 무관, 모션 감소 시 생략) */
export const INTRO_MS = 1400

const PALETTE_NAMES = [
  'px-void', 'px-wall', 'px-wall-top', 'px-wood', 'px-wood-2', 'px-carpet', 'px-carpet-2', 'px-tile', 'px-tile-2',
  'px-tile-v', 'px-tile-s', 'px-concrete', 'px-concrete-2', 'px-desk', 'px-desk-edge', 'px-monitor', 'px-screen',
  'px-plant', 'px-plant-2', 'px-label-bg', 'px-label-ink', 'px-shadow', 'px-cast', 'px-wallface', 'px-wallface-2',
  'px-window', 'px-window-2', 'px-frame', 'px-light', 'px-lamp', 'px-night', 'px-outline',
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

/** 사람마다 다른 외형(작업 ID 해시). 상태와 무관하다 */
const SKIN = ['#f3cfae', '#e0aa82', '#b67b55', '#7e5236']
const HAIR = ['#2b2420', '#5a3a22', '#8a5a2b', '#d6b46a', '#3c3f52', '#7b2f3a', '#c75b39']
const CHAIR = ['#3d4a63', '#4a3d5e', '#2f4f4f', '#5b4636']
function hash(text: string): number {
  let h = 0
  for (let i = 0; i < text.length; i++) h = (h * 31 + text.charCodeAt(i)) | 0
  return Math.abs(h)
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

function rect(ctx: CanvasRenderingContext2D, color: string, x: number, y: number, w: number, h: number) {
  ctx.fillStyle = color
  ctx.fillRect(x, y, w, h)
}

// ── 사람과 책상 ──────────────────────────────────────

/** 의자 등받이 → 사람(3/4 정면) → 책상·모니터 순서로 겹친다 */
function workstation(ctx: CanvasRenderingContext2D, seat: Seat, task: Task, p: Palette, frame: number) {
  const x = seat.tx * TILE
  const y = seat.ty * TILE
  const h = hash(task.id)
  const px = x + 16
  const py = y + 2
  const dim = task.state === 'cancelled' || task.state === 'superseded'
  const running = task.state === 'running'
  const alpha = dim ? 0.45 : 1
  ctx.globalAlpha = alpha

  // 의자 등받이
  rect(ctx, p['px-outline'], px - 1, py + 7, 18, 16)
  rect(ctx, CHAIR[h % CHAIR.length], px, py + 8, 16, 14)
  rect(ctx, 'rgb(255 255 255 / 0.12)', px + 1, py + 9, 14, 2)

  // 몸(역할 색 셔츠 + 오른쪽 음영) + 팔
  const shirt = roleColor(p, task.role)
  const leftUp = running && frame % 2 === 1 ? 1 : 0
  const rightUp = running && frame % 2 === 0 ? 1 : 0
  rect(ctx, p['px-outline'], px + 1, py + 13, 14, 12)
  rect(ctx, shirt, px + 2, py + 14, 12, 11)
  rect(ctx, 'rgb(0 0 0 / 0.18)', px + 10, py + 14, 4, 11)
  rect(ctx, 'rgb(255 255 255 / 0.2)', px + 7, py + 14, 2, 3)
  rect(ctx, p['px-outline'], px - 1, py + 16 + leftUp, 4, 8)
  rect(ctx, p['px-outline'], px + 13, py + 16 + rightUp, 4, 8)
  rect(ctx, shirt, px, py + 17 + leftUp, 2, 5)
  rect(ctx, shirt, px + 14, py + 17 + rightUp, 2, 5)

  // 머리: 외곽선 → 얼굴 → 머리 모양(4종)
  const skin = SKIN[h % SKIN.length]
  rect(ctx, p['px-outline'], px + 2, py - 1, 12, 14)
  rect(ctx, skin, px + 3, py + 2, 10, 10)
  const hair = HAIR[(h >> 3) % HAIR.length]
  const style = (h >> 5) % 4
  rect(ctx, hair, px + 3, py, 10, 4)
  if (style === 0) rect(ctx, hair, px + 3, py + 3, 2, 3)
  if (style === 1) {
    rect(ctx, hair, px + 3, py + 3, 2, 8)
    rect(ctx, hair, px + 11, py + 3, 2, 8)
  }
  if (style === 2) rect(ctx, hair, px + 6, py - 3, 4, 3)
  if (style === 3) {
    rect(ctx, shirt, px + 2, py - 1, 12, 3)
    rect(ctx, shirt, px + 10, py + 1, 5, 2)
  }
  rect(ctx, '#1d1714', px + 5, py + 7, 2, 2)
  rect(ctx, '#1d1714', px + 9, py + 7, 2, 2)
  rect(ctx, 'rgb(240 120 120 / 0.35)', px + 4, py + 9, 2, 1)
  rect(ctx, 'rgb(240 120 120 / 0.35)', px + 10, py + 9, 2, 1)
  if (running) {
    // 실행 중이면 모니터 빛이 얼굴에 비친다
    ctx.globalAlpha = 0.28
    rect(ctx, p['px-screen'], px + 3, py + 6, 10, 6)
    ctx.globalAlpha = alpha
  }

  // 책상 + 그림자, 모니터 뒷면, 소품(사람마다 다름)
  cast(ctx, p, x + 3, y + 42, 42, 4)
  box(ctx, p, x + 3, y + 27, 42, 14, p['px-desk'], p['px-desk-edge'])
  rect(ctx, 'rgb(255 255 255 / 0.15)', x + 4, y + 27, 40, 1)
  rect(ctx, p['px-outline'], x + 15, y + 19, 18, 11)
  rect(ctx, p['px-monitor'], x + 16, y + 20, 16, 9)
  rect(ctx, p['px-outline'], x + 22, y + 29, 4, 3)
  rect(ctx, '#d9dde2', x + 17, y + 32, 14, 3)
  if (h % 3 !== 0) {
    rect(ctx, p['px-outline'], x + 36, y + 30, 5, 6)
    rect(ctx, h % 2 ? '#f2f2f2' : '#e07a5f', x + 37, y + 31, 3, 4)
  }
  if (h % 4 === 0) {
    rect(ctx, '#ffffff', x + 6, y + 30, 8, 6)
    rect(ctx, '#d8d2c0', x + 7, y + 31, 6, 1)
  }
  rect(ctx, p['px-outline'], x + 8, y + 22, 2, 8)
  rect(ctx, '#e8c26a', x + 6, y + 20, 6, 3)
  ctx.globalAlpha = 1
}

/** 실행 중인 책상에만 켜지는 램프·모니터 빛(가산 합성). 밤 테마에서 더 강하다 */
function lights(ctx: CanvasRenderingContext2D, layout: OfficeLayout, tasks: ReadonlyMap<string, Task>, p: Palette) {
  const night = p['px-night'] === '1'
  ctx.globalCompositeOperation = 'lighter'
  for (const seat of layout.seats) {
    if (tasks.get(seat.taskId)?.state !== 'running') continue
    const cx = seat.tx * TILE + 24
    const cy = seat.ty * TILE + 26
    const radius = night ? 46 : 30
    const g = ctx.createRadialGradient(cx, cy, 2, cx, cy, radius)
    g.addColorStop(0, night ? 'rgb(255 200 120 / 0.55)' : 'rgb(255 230 170 / 0.28)')
    g.addColorStop(1, 'rgb(255 200 120 / 0)')
    ctx.fillStyle = g
    ctx.fillRect(cx - radius, cy - radius, radius * 2, radius * 2)
    const m = ctx.createRadialGradient(cx, cy - 6, 1, cx, cy - 6, 18)
    m.addColorStop(0, 'rgb(140 210 255 / 0.45)')
    m.addColorStop(1, 'rgb(140 210 255 / 0)')
    ctx.fillStyle = m
    ctx.fillRect(cx - 18, cy - 24, 36, 36)
  }
  ctx.globalCompositeOperation = 'source-over'
}

/** 첫 진입: 어두운 사무실에 방마다 차례로 불이 켜진다(0→1). 장식이며 상태와 무관 */
function intro(ctx: CanvasRenderingContext2D, layout: OfficeLayout, t: number) {
  if (t >= 1) return
  const rooms = layout.map.rooms
  rooms.forEach((r, i) => {
    const start = (i / rooms.length) * 0.65
    const local = Math.min(1, Math.max(0, (t - start) / 0.35))
    const flicker = local > 0 && local < 0.4 && seeded(i, Math.floor(t * 40)) > 0.5 ? 0.15 : 0
    const dark = (1 - local) * 0.82 + flicker
    if (dark <= 0) return
    ctx.fillStyle = `rgb(6 8 14 / ${dark})`
    ctx.fillRect(r.x * TILE, r.y * TILE, r.w * TILE, r.h * TILE)
  })
}

function packet(ctx: CanvasRenderingContext2D, pk: Packet, now: number, p: Palette) {
  const at = (t: number) => {
    const e = 1 - (1 - t) ** 3
    return { x: pk.from.x + (pk.to.x - pk.from.x) * e, y: pk.from.y + (pk.to.y - pk.from.y) * e - Math.sin(Math.PI * t) * 18 }
  }
  const t = Math.min(1, (now - pk.startedAt) / PACKET_MS)
  const color = pk.kind === 'alert' ? toneColor(p, 'danger') : pk.kind === 'done' ? toneColor(p, 'ok') : toneColor(p, 'active')
  for (let k = 3; k > 0; k--) {
    const trail = at(Math.max(0, t - k * 0.05))
    ctx.globalAlpha = 0.12 * (4 - k)
    rect(ctx, color, trail.x - 2, trail.y - 2, 4, 4)
  }
  ctx.globalAlpha = 1
  const { x, y } = at(t)
  rect(ctx, p['px-outline'], x - 5, y - 6, 10, 12)
  rect(ctx, '#ffffff', x - 4, y - 5, 8, 10)
  rect(ctx, color, x - 4, y - 5, 8, 2)
  rect(ctx, '#c9ced4', x - 2, y - 1, 5, 1)
  rect(ctx, '#c9ced4', x - 2, y + 2, 4, 1)
}

// ── 화면 좌표 층: 말풍선·명판·이름표(선명한 글자) ─────

/** 상태 표식. 실행 중은 손 움직임과 빛으로 보여 주고 말풍선은 없다 */
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

/** 픽셀 말풍선: 각진 테두리 + 꼬리 + 그림자 */
function bubble(ctx: CanvasRenderingContext2D, x: number, y: number, size: number, glyph: string, color: string, p: Palette) {
  const u = Math.max(2, Math.round(size / 9))
  rect(ctx, 'rgb(0 0 0 / 0.25)', x + u, y + u, size, size)
  rect(ctx, p['px-outline'], x - u, y, size + 2 * u, size)
  rect(ctx, p['px-outline'], x, y - u, size, size + 2 * u)
  rect(ctx, '#fffdf6', x, y, size, size)
  rect(ctx, p['px-outline'], x + u, y + size + u, u * 2, u)
  ctx.fillStyle = color
  ctx.font = `800 ${Math.round(size * 0.72)}px system-ui, sans-serif`
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(glyph, x + size / 2, y + size / 2 + 1)
}

function seatOverlay(ctx: CanvasRenderingContext2D, seat: Seat, task: Task, p: Palette, selected: boolean, px: number) {
  const b = BUBBLE[task.state]
  const cx = seat.x + seat.w / 2
  if (b) {
    const size = Math.max(14, Math.round(px * 0.7))
    bubble(ctx, cx + px * 0.38, seat.y - size * 0.35, size, b.glyph, toneColor(p, b.tone), p)
  }
  if (selected) {
    ctx.strokeStyle = p.focus
    ctx.lineWidth = 3
    ctx.setLineDash([6, 4])
    roundRect(ctx, seat.x + 1, seat.y - 4, seat.w - 2, seat.h + 6, 8)
    ctx.stroke()
    ctx.setLineDash([])
  }
  // 이름표는 충분히 클 때만(작으면 DOM 좌석 목록이 같은 정보를 준다)
  if (px < 18) return
  const state = TASK_STATE[task.state]
  const fontPx = Math.round(Math.min(13, Math.max(10, px * 0.4)))
  ctx.font = `650 ${fontPx}px system-ui, sans-serif`
  ctx.textAlign = 'center'
  ctx.textBaseline = 'top'
  const label = truncate(ctx, task.title, seat.w - 16)
  const lw = Math.min(seat.w - 2, ctx.measureText(label).width + 20)
  const ly = seat.y + seat.h
  ctx.fillStyle = 'rgb(0 0 0 / 0.22)'
  roundRect(ctx, cx - lw / 2 + 1, ly + 2, lw, fontPx * 2.6, 6)
  ctx.fill()
  ctx.fillStyle = p['px-label-bg']
  roundRect(ctx, cx - lw / 2, ly, lw, fontPx * 2.6, 6)
  ctx.fill()
  ctx.fillStyle = roleColor(p, task.role)
  ctx.beginPath()
  ctx.arc(cx - lw / 2 + 8, ly + fontPx * 0.75, 3, 0, Math.PI * 2)
  ctx.fill()
  ctx.fillStyle = p['px-label-ink']
  ctx.fillText(label, cx + 5, ly + 3)
  ctx.fillStyle = toneColor(p, state.tone)
  ctx.font = `800 ${fontPx - 1}px system-ui, sans-serif`
  ctx.fillText(`${state.glyph} ${state.text}`, cx, ly + fontPx + 6)
}

/** 방 이름표: 벽면 왼쪽(창은 오른쪽에만 둔다). 방 폭을 넘지 않게 줄인다 */
function roomSigns(ctx: CanvasRenderingContext2D, layout: OfficeLayout, counts: Map<string, number>) {
  const px = TILE * layout.scale
  const fontPx = Math.round(Math.min(14, Math.max(10, px * 0.4)))
  ctx.font = `800 ${fontPx}px system-ui, sans-serif`
  ctx.textAlign = 'left'
  ctx.textBaseline = 'middle'
  for (const z of layout.zones) {
    const n = counts.get(z.id) ?? 0
    const more = layout.overflow[z.id] ? ` +${layout.overflow[z.id]}` : ''
    const room = layout.map.rooms.find((r) => r.id === z.id)
    const plateW = room ? Math.min(z.w - 12, 5 * px - 8) : z.w - 12
    const text = truncate(ctx, n ? `${z.label}  ${n}${more}` : z.label, plateW - 18)
    const w = Math.min(plateW, ctx.measureText(text).width + 18)
    const h = fontPx + 10
    const x = z.x + 6
    const y = z.y + (WALL_FACE_ROWS * px - h) / 2
    ctx.fillStyle = 'rgb(0 0 0 / 0.25)'
    roundRect(ctx, x + 2, y + 2, w, h, 4)
    ctx.fill()
    ctx.fillStyle = n ? '#1f2a22' : 'rgb(31 42 34 / 0.75)'
    roundRect(ctx, x, y, w, h, 4)
    ctx.fill()
    ctx.strokeStyle = n ? '#c9a84a' : 'rgb(201 168 74 / 0.4)'
    ctx.lineWidth = 1.5
    ctx.stroke()
    ctx.fillStyle = n ? '#f3e7c3' : 'rgb(243 231 195 / 0.65)'
    ctx.fillText(text, x + 9, y + h / 2 + 0.5)
  }
}

/** 지도 바깥은 단색 */
function backdrop(ctx: CanvasRenderingContext2D, layout: OfficeLayout, p: Palette) {
  rect(ctx, p['px-void'], 0, 0, layout.width, layout.height)
}

export interface SceneState {
  layout: OfficeLayout
  tasks: ReadonlyMap<string, Task>
  selectedTaskId: string | null
  packets: readonly Packet[]
  frame: number
  now: number
  /** 첫 진입 인트로 진행도(0→1). 생략하면 1 */
  intro?: number
}

/** dpr은 캔버스 픽셀 비율. 모든 좌표는 CSS 픽셀 기준으로 받는다 */
export function drawScene(ctx: CanvasRenderingContext2D, scene: SceneState, p: Palette, dpr = 1): void {
  const { layout } = scene
  const s = layout.scale
  const introT = scene.intro ?? 1
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.imageSmoothingEnabled = false
  backdrop(ctx, layout, p)

  // 지도 좌표
  ctx.setTransform(dpr * s, 0, 0, dpr * s, dpr * layout.ox, dpr * layout.oy)
  const layer = staticLayer(layout.map, p)
  if (layer) ctx.drawImage(layer, 0, 0)
  else drawStatic(ctx, layout.map, p)
  // 아래쪽 좌석이 위쪽 좌석을 가리도록 y 순서로
  for (const seat of [...layout.seats].sort((a, b) => a.ty - b.ty)) {
    const task = scene.tasks.get(seat.taskId)
    if (task) workstation(ctx, seat, task, p, scene.frame)
  }
  lights(ctx, layout, scene.tasks, p)
  scene.packets.forEach((pk) => packet(ctx, pk, scene.now, p))
  intro(ctx, layout, introT)

  // 화면 좌표: 선명한 글자·말풍선
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  if (introT < 0.6) return
  const counts = new Map<string, number>()
  scene.tasks.forEach((t) => {
    if (t.state !== 'superseded') counts.set(ROLE_ZONE[t.role], (counts.get(ROLE_ZONE[t.role]) ?? 0) + 1)
  })
  roomSigns(ctx, layout, counts)
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
