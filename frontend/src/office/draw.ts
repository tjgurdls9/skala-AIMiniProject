import type { Role, RunEvent, Task } from '../api/types'
import { ROLE, TASK_STATE, type Tone } from '../model/labels'
import { ROLE_ZONE, zoneCenter, type OfficeLayout, type Seat, type Zone, type ZoneId } from './layout'

/** 수신한 공개 사건에 대한 연출만. 아직 일어나지 않은 성공을 그리지 않는다. */
export interface Packet {
  from: { x: number; y: number }
  to: { x: number; y: number }
  startedAt: number
  kind: 'evidence' | 'report' | 'done' | 'alert'
}

export const PACKET_MS = 900

type Palette = Record<string, string>

export function readPalette(el: Element): Palette {
  const style = getComputedStyle(el)
  const names = [
    'office-floor', 'office-wall', 'office-desk', 'office-room-line', 'ink', 'ink-2', 'ink-3', 'surface', 'focus',
    'role-planner', 'role-supervisor', 'role-builder', 'role-validator', 'role-security', 'role-release',
    'tone-neutral', 'tone-active', 'tone-ok', 'tone-warn', 'tone-danger', 'tone-wait',
  ]
  return Object.fromEntries(names.map((n) => [n, style.getPropertyValue(`--${n}`).trim() || '#888']))
}

const roleColor = (p: Palette, role: Role) => p[`role-${role}`]
const toneColor = (p: Palette, tone: Tone) => p[`tone-${tone}`]

function drawZones(ctx: CanvasRenderingContext2D, layout: OfficeLayout, p: Palette, occupied: Set<ZoneId>) {
  ctx.fillStyle = p['office-wall']
  ctx.fillRect(0, 0, layout.width, layout.height)
  for (const z of layout.zones) {
    ctx.fillStyle = p['office-floor']
    ctx.fillRect(z.x + 3, z.y + 3, z.w - 6, z.h - 6)
    ctx.strokeStyle = p['office-room-line']
    ctx.lineWidth = 1
    ctx.strokeRect(z.x + 3.5, z.y + 3.5, z.w - 7, z.h - 7)
    ctx.fillStyle = p['ink-2']
    ctx.font = '600 12px system-ui, sans-serif'
    ctx.textBaseline = 'middle'
    ctx.fillText(z.label, z.x + 12, z.y + 16)
    drawFurniture(ctx, z, p)
    if (!occupied.has(z.id)) {
      ctx.fillStyle = p['ink-3']
      ctx.font = '12px system-ui, sans-serif'
      ctx.fillText('이 Sprint 작업 없음', z.x + 12, z.y + 36)
    }
  }
}

/** 구역을 알아보게 하는 정적 가구. 상태를 나타내지 않는다. */
function drawFurniture(ctx: CanvasRenderingContext2D, z: Zone, p: Palette) {
  const cx = z.x + z.w / 2
  const bottom = z.y + z.h - 14
  ctx.fillStyle = p['office-desk']
  ctx.globalAlpha = 0.45
  if (z.id === 'meeting') {
    // 회의 탁자 + 명세 보드
    ctx.fillRect(cx - z.w * 0.3, bottom - 26, z.w * 0.6, 16)
    ctx.fillRect(z.x + z.w - 30, z.y + 34, 14, 40)
  } else if (z.id === 'release') {
    // 출시 게이트 아치
    ctx.fillRect(cx - 34, bottom - 70, 8, 70)
    ctx.fillRect(cx + 26, bottom - 70, 8, 70)
    ctx.fillRect(cx - 34, bottom - 78, 68, 10)
  } else if (z.id === 'validate' || z.id === 'security') {
    // 분리된 검토실: 문 표시
    ctx.fillRect(z.x + 3, z.y + z.h / 2 - 14, 4, 28)
  } else {
    // 구현 구역 근거 보드
    ctx.fillRect(z.x + z.w - 44, z.y + 8, 32, 14)
  }
  ctx.globalAlpha = 1
}

function drawSeat(ctx: CanvasRenderingContext2D, seat: Seat, task: Task, p: Palette, selected: boolean, frame: number) {
  const s = seat.w / 64
  const cx = seat.x + seat.w / 2
  const state = TASK_STATE[task.state]
  const typing = task.state === 'running' && frame % 2 === 1
  // 책상·모니터
  ctx.fillStyle = p['office-desk']
  ctx.fillRect(seat.x + 6 * s, seat.y + 40 * s, 52 * s, 10 * s)
  ctx.fillStyle = task.state === 'running' ? toneColor(p, 'active') : p['ink-3']
  ctx.fillRect(cx - 9 * s, seat.y + 30 * s, 18 * s, 11 * s)
  // 사람: 역할 색 몸통 + 머리. 실행 중일 때만 손이 움직인다(유휴 동작 없음)
  ctx.fillStyle = roleColor(p, task.role)
  ctx.fillRect(cx - 8 * s, seat.y + 18 * s, 16 * s, 14 * s)
  ctx.beginPath()
  ctx.arc(cx, seat.y + 12 * s, 6 * s, 0, Math.PI * 2)
  ctx.fill()
  if (task.state === 'running') {
    ctx.fillRect(cx + (typing ? 6 : 3) * s, seat.y + 36 * s, 4 * s, 3 * s)
  }
  // 역할 기호(색 외 표식)
  ctx.fillStyle = p.surface
  ctx.font = `700 ${Math.max(8, 9 * s)}px system-ui, sans-serif`
  ctx.textAlign = 'center'
  ctx.fillText(ROLE[task.role].glyph, cx, seat.y + 25 * s)
  // 상태 기호 + 짧은 상태명
  ctx.fillStyle = toneColor(p, state.tone)
  ctx.font = `700 ${Math.max(9, 11 * s)}px system-ui, sans-serif`
  ctx.fillText(`${state.glyph} ${state.text}`, cx, seat.y + 60 * s)
  ctx.textAlign = 'start'
  if (selected) {
    ctx.strokeStyle = p.focus
    ctx.lineWidth = 2
    ctx.strokeRect(seat.x + 1, seat.y + 1, seat.w - 2, seat.h - 2)
  }
}

function drawPacket(ctx: CanvasRenderingContext2D, packet: Packet, now: number, p: Palette) {
  const t = Math.min(1, (now - packet.startedAt) / PACKET_MS)
  const ease = 1 - (1 - t) ** 3
  const x = packet.from.x + (packet.to.x - packet.from.x) * ease
  const y = packet.from.y + (packet.to.y - packet.from.y) * ease - Math.sin(Math.PI * t) * 18
  const color = packet.kind === 'alert' ? toneColor(p, 'danger') : packet.kind === 'done' ? toneColor(p, 'ok') : toneColor(p, 'active')
  ctx.fillStyle = color
  ctx.fillRect(x - 6, y - 4, 12, 9)
  ctx.strokeStyle = p.surface
  ctx.strokeRect(x - 6, y - 4, 12, 9)
}

export interface SceneState {
  layout: OfficeLayout
  tasks: ReadonlyMap<string, Task>
  selectedTaskId: string | null
  packets: readonly Packet[]
  frame: number
  now: number
}

export function drawScene(ctx: CanvasRenderingContext2D, scene: SceneState, p: Palette): void {
  const occupied = new Set(scene.layout.seats.map((s) => s.zone))
  drawZones(ctx, scene.layout, p, occupied)
  for (const seat of scene.layout.seats) {
    const task = scene.tasks.get(seat.taskId)
    if (task) drawSeat(ctx, seat, task, p, task.id === scene.selectedTaskId, scene.frame)
  }
  scene.packets.forEach((packet) => drawPacket(ctx, packet, scene.now, p))
}

/** 사건을 장면 연출로 바꾼다. 장면에 없는 작업·근거 없는 사건은 연출하지 않는다. */
export function packetFor(event: RunEvent, layout: OfficeLayout, tasks: ReadonlyMap<string, Task>, now: number): Packet | null {
  const task = event.task_id ? tasks.get(event.task_id) : undefined
  const seat = task ? layout.seats.find((s) => s.taskId === task.id) : undefined
  if (!task || !seat) return null
  const from = { x: seat.x + seat.w / 2, y: seat.y + seat.h / 2 }
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
      return { from, to: { x: from.x, y: from.y - 30 }, startedAt: now, kind: task.state === 'failed' ? 'alert' : task.state === 'succeeded' ? 'done' : 'evidence' }
    case 'warning':
    case 'operation_uncertain':
      return { from, to: { x: from.x, y: from.y - 30 }, startedAt: now, kind: 'alert' }
    default:
      return null
  }
}
