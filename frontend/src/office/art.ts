// 사무실의 정적 그림(바닥·벽면·가구). 상태를 나타내지 않는 배경이며 지도 해상도에서 한 번 그려 캐시한다.
// 빛은 위(창)에서 온다고 통일하고, 그림자는 검정 대신 차가운 색조(--px-cast)를 쓴다.
import { TILE, WALL_FACE_ROWS, type Room, type TileMap } from './layout'

export type Palette = Record<string, string>

/** 타일마다 같은 값을 내는 결정적 난수(매 프레임 같은 그림) */
export function seeded(x: number, y: number, salt = 0): number {
  let h = (x * 374761393 + y * 668265263 + salt * 2147483647) | 0
  h = (h ^ (h >>> 13)) * 1274126177
  return ((h ^ (h >>> 16)) >>> 0) / 4294967295
}

function rect(ctx: CanvasRenderingContext2D, color: string, x: number, y: number, w: number, h: number) {
  ctx.fillStyle = color
  ctx.fillRect(x, y, w, h)
}

/** 외곽선이 있는 상자: 윗면 하이라이트 + 아래 어두운 면 */
export function box(ctx: CanvasRenderingContext2D, p: Palette, x: number, y: number, w: number, h: number, top: string, side: string) {
  rect(ctx, p['px-outline'], x - 1, y - 1, w + 2, h + 2)
  rect(ctx, side, x, y, w, h)
  rect(ctx, top, x, y, w, Math.max(2, Math.round(h * 0.6)))
}

/** 물체 아래쪽에 붙는 차가운 그림자(빛이 위에서 오므로 아래로) */
export function cast(ctx: CanvasRenderingContext2D, p: Palette, x: number, y: number, w: number, h = 3) {
  rect(ctx, p['px-cast'], x + 1, y, w, h)
}

// ── 바닥 ──────────────────────────────────────────────

function planks(ctx: CanvasRenderingContext2D, r: Room, a: string, b: string, y0: number) {
  const x0 = r.x * TILE
  const W = r.w * TILE
  const H = (r.y + r.h) * TILE - y0
  rect(ctx, a, x0, y0, W, H)
  for (let row = 0; row * 5 < H; row++) {
    const y = y0 + row * 5
    let x = -Math.floor(seeded(row, r.x) * 30)
    while (x < W) {
      const len = 24 + Math.floor(seeded(x, row, r.y) * 22)
      const tone = seeded(row, x, 7)
      ctx.globalAlpha = 0.18 + tone * 0.25
      rect(ctx, tone > 0.5 ? b : '#ffffff', x0 + Math.max(0, x), y, Math.min(len, W - Math.max(0, x)), 4)
      ctx.globalAlpha = 1
      if (x + len < W) rect(ctx, b, x0 + x + len, y, 1, 4)
      x += len + 1
    }
    rect(ctx, b, x0, y + 4, W, 1)
  }
}

function carpet(ctx: CanvasRenderingContext2D, r: Room, a: string, b: string, y0: number) {
  const x0 = r.x * TILE
  const W = r.w * TILE
  const H = (r.y + r.h) * TILE - y0
  rect(ctx, a, x0, y0, W, H)
  for (let y = 0; y < H; y += 2) {
    for (let x = (y / 2) % 2 ? 1 : 0; x < W; x += 4) {
      if (seeded(x, y, 3) > 0.55) rect(ctx, b, x0 + x, y0 + y, 1, 1)
    }
  }
  // 테두리 무늬
  ctx.strokeStyle = b
  ctx.lineWidth = 2
  ctx.strokeRect(x0 + 5, y0 + 5, W - 10, H - 10)
}

function tiles(ctx: CanvasRenderingContext2D, r: Room, a: string, b: string, y0: number, size: number) {
  const x0 = r.x * TILE
  const W = r.w * TILE
  const H = (r.y + r.h) * TILE - y0
  rect(ctx, a, x0, y0, W, H)
  for (let y = 0; y < H; y += size) {
    for (let x = 0; x < W; x += size) {
      if (seeded(x, y, r.x) > 0.6) {
        ctx.globalAlpha = 0.35
        rect(ctx, b, x0 + x + 1, y0 + y + 1, size - 2, size - 2)
        ctx.globalAlpha = 1
      }
    }
    rect(ctx, b, x0, y0 + y, W, 1)
  }
  for (let x = 0; x < W; x += size) rect(ctx, b, x0 + x, y0, 1, H)
}

function floor(ctx: CanvasRenderingContext2D, r: Room, p: Palette) {
  const y0 = (r.y + WALL_FACE_ROWS) * TILE
  if (r.id === 'meeting') carpet(ctx, r, p['px-carpet'], p['px-carpet-2'], y0)
  else if (r.id === 'build') planks(ctx, r, p['px-wood'], p['px-wood-2'], y0)
  else if (r.id === 'validate') tiles(ctx, r, p['px-tile'], p['px-tile-v'], y0, 12)
  else if (r.id === 'security') tiles(ctx, r, p['px-tile'], p['px-tile-s'], y0, 12)
  else tiles(ctx, r, p['px-concrete'], p['px-concrete-2'], y0, 16)
}

// ── 벽면(3/4 시점) ─────────────────────────────────────

function windowOn(ctx: CanvasRenderingContext2D, p: Palette, x: number, y: number, w: number) {
  rect(ctx, p['px-frame'], x - 2, y - 2, w + 4, 18)
  rect(ctx, p['px-window'], x, y, w, 14)
  rect(ctx, p['px-window-2'], x, y, w, 5)
  // 창살과 하늘 표식(밤에는 별, 낮에는 구름)
  rect(ctx, p['px-frame'], x + Math.floor(w / 2) - 1, y, 2, 14)
  const night = p['px-night'] === '1'
  for (let i = 0; i < 3; i++) {
    const sx = x + 3 + Math.floor(seeded(x, i) * (w - 6))
    const sy = y + 2 + Math.floor(seeded(i, x) * 9)
    rect(ctx, night ? '#fff6c8' : '#ffffff', sx, sy, night ? 1 : 4, 1)
  }
}

function frame(ctx: CanvasRenderingContext2D, p: Palette, x: number, y: number, color: string) {
  rect(ctx, p['px-frame'], x, y, 12, 10)
  rect(ctx, color, x + 2, y + 2, 8, 6)
  rect(ctx, '#ffffff', x + 3, y + 3, 3, 2)
}

function clock(ctx: CanvasRenderingContext2D, p: Palette, x: number, y: number) {
  rect(ctx, p['px-outline'], x, y, 10, 10)
  rect(ctx, '#f4f1e6', x + 1, y + 1, 8, 8)
  rect(ctx, p['px-outline'], x + 4, y + 2, 1, 4)
  rect(ctx, p['px-outline'], x + 4, y + 5, 3, 1)
}

function wallFace(ctx: CanvasRenderingContext2D, r: Room, p: Palette) {
  const x0 = r.x * TILE
  const y0 = r.y * TILE
  const W = r.w * TILE
  const H = WALL_FACE_ROWS * TILE
  rect(ctx, p['px-wallface'], x0, y0, W, H)
  rect(ctx, p['px-wallface-2'], x0, y0 + H - 9, W, 9) // 징두리판
  rect(ctx, p['px-outline'], x0, y0 + H - 9, W, 1)
  rect(ctx, p['px-shadow'], x0, y0 + H, W, 4) // 벽 아래 접촉 그림자
  // 창은 방 폭에 맞춰 1~3개, 사이에 액자·시계
  const count = Math.max(1, Math.min(3, Math.floor(r.w / 5)))
  const gap = W / count
  for (let i = 0; i < count; i++) {
    const wx = Math.round(x0 + gap * i + gap / 2 - 13)
    if (r.w >= 4) windowOn(ctx, p, wx, y0 + 6, 26)
  }
  if (r.id === 'build') clock(ctx, p, x0 + W - 18, y0 + 8)
  if (r.id === 'meeting' && r.w >= 6) frame(ctx, p, x0 + 6, y0 + 8, p['role-planner'])
  if (r.id === 'release') frame(ctx, p, x0 + 4, y0 + 8, p['role-release'])
}

/** 창에서 바닥으로 떨어지는 빛 웅덩이(사다리꼴) */
function windowLight(ctx: CanvasRenderingContext2D, r: Room, p: Palette) {
  const x0 = r.x * TILE
  const y0 = (r.y + WALL_FACE_ROWS) * TILE
  const W = r.w * TILE
  const count = Math.max(1, Math.min(3, Math.floor(r.w / 5)))
  const gap = W / count
  ctx.fillStyle = p['px-light']
  for (let i = 0; i < count; i++) {
    const cx = x0 + gap * i + gap / 2
    ctx.beginPath()
    ctx.moveTo(cx - 13, y0)
    ctx.lineTo(cx + 13, y0)
    ctx.lineTo(cx + 22, y0 + 46)
    ctx.lineTo(cx - 4, y0 + 46)
    ctx.closePath()
    ctx.fill()
  }
}

// ── 가구 ──────────────────────────────────────────────

export function plant(ctx: CanvasRenderingContext2D, p: Palette, x: number, y: number, big = false) {
  const s = big ? 1.4 : 1
  cast(ctx, p, x + 2, y + 15 * s, 12 * s)
  box(ctx, p, x + 4 * s, y + 9 * s, 8 * s, 7 * s, '#c7764a', '#9b5634')
  rect(ctx, p['px-outline'], x + 1, y - 1, 14 * s, 11 * s)
  rect(ctx, p['px-plant'], x + 2, y, 12 * s, 9 * s)
  rect(ctx, p['px-plant-2'], x + 4 * s, y - 2 * s, 6 * s, 5 * s)
  rect(ctx, p['px-plant-2'], x + 2, y + 3 * s, 3 * s, 3 * s)
  rect(ctx, p['px-plant-2'], x + 10 * s, y + 4 * s, 3 * s, 3 * s)
}

function chairTop(ctx: CanvasRenderingContext2D, p: Palette, x: number, y: number, color: string) {
  box(ctx, p, x, y, 8, 6, color, p['px-outline'])
}

function meetingRoom(ctx: CanvasRenderingContext2D, r: Room, p: Palette, bottom: number) {
  const W = r.w * TILE
  const x0 = r.x * TILE
  // 화이트보드 + 포스트잇
  const bw = Math.min(W - 40, 64)
  const bx = x0 + W - bw - 22
  const by = r.y * TILE + 4
  rect(ctx, p['px-outline'], bx - 1, by - 1, bw + 2, 18)
  rect(ctx, '#f6f5ef', bx, by, bw, 16)
  const notes = ['#ffd166', '#8ecae6', '#f4978e', '#b9e28c']
  for (let i = 0; i < 4 && i * 11 + 4 < bw - 8; i++) rect(ctx, notes[i], bx + 4 + i * 11, by + 3 + (i % 2) * 5, 7, 6)
  // 러그 + 회의 탁자 + 의자 + 노트북
  const tw = Math.min(W - 28, 100)
  const tx = x0 + (W - tw) / 2
  const ty = bottom - 52
  ctx.globalAlpha = 0.35
  rect(ctx, p['role-planner'], tx - 8, ty - 8, tw + 16, 44)
  ctx.globalAlpha = 1
  for (let i = 0; i < Math.floor(tw / 22); i++) {
    chairTop(ctx, p, tx + 8 + i * 22, ty - 6, '#5a6b84')
    chairTop(ctx, p, tx + 8 + i * 22, ty + 28, '#5a6b84')
  }
  cast(ctx, p, tx, ty + 24, tw, 4)
  box(ctx, p, tx, ty, tw, 24, p['px-desk'], p['px-desk-edge'])
  rect(ctx, '#cfd6de', tx + 10, ty + 6, 12, 8)
  rect(ctx, '#2c3138', tx + 11, ty + 7, 10, 5)
  rect(ctx, '#ffffff', tx + tw - 26, ty + 8, 10, 7)
  rect(ctx, '#e8e2d0', tx + tw - 24, ty + 6, 10, 7)
  plant(ctx, p, x0 + 3, bottom - 20, true)
}

function buildRoom(ctx: CanvasRenderingContext2D, r: Room, p: Palette, bottom: number) {
  const x0 = r.x * TILE
  const right = (r.x + r.w) * TILE
  // 책장
  const bx = x0 + 4
  const by = bottom - 40
  cast(ctx, p, bx, by + 36, 48, 4)
  box(ctx, p, bx, by, 48, 36, p['px-desk-edge'], p['px-outline'])
  const books = [p['role-builder'], p['role-planner'], p['role-validator'], p['role-security'], '#d1495b', '#edae49']
  for (let shelf = 0; shelf < 3; shelf++) {
    for (let i = 0; i < 8; i++) {
      const h = 7 + Math.floor(seeded(i, shelf, 11) * 3)
      rect(ctx, books[(i + shelf) % books.length], bx + 3 + i * 5, by + 3 + shelf * 11 + (10 - h), 4, h)
    }
    rect(ctx, p['px-desk'], bx + 2, by + 13 + shelf * 11, 44, 1)
  }
  // 커피머신 + 정수기 코너
  const cx = right - 44
  const cy = bottom - 34
  cast(ctx, p, cx, cy + 22, 16)
  box(ctx, p, cx, cy, 16, 22, '#3d4148', '#23262b')
  rect(ctx, '#d64545', cx + 3, cy + 4, 3, 2)
  rect(ctx, '#f2f2f2', cx + 6, cy + 13, 4, 4)
  cast(ctx, p, cx + 22, cy + 22, 12)
  box(ctx, p, cx + 22, cy + 8, 12, 14, '#e9eef2', '#c8d0d6')
  rect(ctx, '#7cc6ec', cx + 23, cy, 10, 9)
  plant(ctx, p, right - 18, bottom - 20, true)
}

function securityRoom(ctx: CanvasRenderingContext2D, r: Room, p: Palette, bottom: number) {
  const x0 = r.x * TILE
  const right = (r.x + r.w) * TILE
  for (let k = 0; k < 2; k++) {
    const sx = x0 + 4 + k * 22
    const sy = bottom - 46
    cast(ctx, p, sx, sy + 42, 18, 4)
    box(ctx, p, sx, sy, 18, 42, '#2b3036', '#16191d')
    for (let i = 0; i < 6; i++) {
      rect(ctx, '#3a4048', sx + 2, sy + 4 + i * 6, 14, 4)
      rect(ctx, i % 3 === 0 ? '#59d185' : p['role-security'], sx + 3, sy + 5 + i * 6, 2, 2)
    }
  }
  // 소화기
  box(ctx, p, right - 12, bottom - 18, 6, 12, '#d64545', '#9e2a2a')
}

function validateRoom(ctx: CanvasRenderingContext2D, r: Room, p: Palette, bottom: number) {
  const x0 = r.x * TILE
  // 검사대 + 돋보기 + 체크리스트
  cast(ctx, p, x0 + 4, bottom - 8, 40, 3)
  box(ctx, p, x0 + 4, bottom - 22, 40, 14, '#d8dde3', '#aeb5bd')
  rect(ctx, p['px-outline'], x0 + 10, bottom - 20, 8, 8)
  rect(ctx, '#bfe3ff', x0 + 11, bottom - 19, 6, 6)
  rect(ctx, p['px-outline'], x0 + 17, bottom - 13, 4, 2)
  rect(ctx, '#ffffff', x0 + 26, bottom - 21, 12, 11)
  for (let i = 0; i < 3; i++) rect(ctx, p['role-validator'], x0 + 28, bottom - 19 + i * 3, 8, 1)
}

function releaseRoom(ctx: CanvasRenderingContext2D, r: Room, p: Palette, bottom: number) {
  const W = r.w * TILE
  const gx = r.x * TILE + W / 2 - 24
  const gy = bottom - 74
  // 발사대 줄무늬 + 게이트 아치
  for (let i = 0; i < 8; i++) rect(ctx, i % 2 ? p['tone-warn'] : '#2b2f35', gx + i * 6, bottom - 10, 6, 5)
  cast(ctx, p, gx, bottom - 5, 48, 3)
  box(ctx, p, gx, gy, 7, 64, '#7d8792', '#56606a')
  box(ctx, p, gx + 41, gy, 7, 64, '#7d8792', '#56606a')
  box(ctx, p, gx, gy, 48, 8, '#9aa4ae', '#56606a')
  rect(ctx, p['role-release'], gx + 8, gy + 9, 32, 2)
}

/** 방 바깥 벽(위에서 본 윗면)과 문 */
function walls(ctx: CanvasRenderingContext2D, map: TileMap, p: Palette) {
  rect(ctx, p['px-wall'], 0, 0, map.w * TILE, map.h * TILE)
  // 벽 윗면 결(은은하게)
  ctx.globalAlpha = 0.35
  for (let y = 0; y < map.h * TILE; y += 8) rect(ctx, p['px-wall-top'], 0, y, map.w * TILE, 1)
  ctx.globalAlpha = 1
}

export function drawStatic(ctx: CanvasRenderingContext2D, map: TileMap, p: Palette): void {
  walls(ctx, map, p)
  for (const d of map.doors) {
    const x = d.x * TILE
    const y = d.y * TILE
    if (d.vertical) rect(ctx, p['px-concrete'], x, y, TILE, d.length * TILE)
    else rect(ctx, p['px-concrete'], x, y, d.length * TILE, TILE)
  }
  for (const r of map.rooms) {
    floor(ctx, r, p)
    wallFace(ctx, r, p)
    windowLight(ctx, r, p)
    // 왼쪽 벽 접촉 그림자
    rect(ctx, p['px-shadow'], r.x * TILE, (r.y + WALL_FACE_ROWS) * TILE, 3, (r.h - WALL_FACE_ROWS) * TILE)
    const bottom = (r.y + r.h) * TILE
    if (r.id === 'meeting') meetingRoom(ctx, r, p, bottom)
    else if (r.id === 'build') buildRoom(ctx, r, p, bottom)
    else if (r.id === 'security') securityRoom(ctx, r, p, bottom)
    else if (r.id === 'validate') validateRoom(ctx, r, p, bottom)
    else releaseRoom(ctx, r, p, bottom)
    if (r.id !== 'build' && r.id !== 'meeting' && r.w >= 5) plant(ctx, p, (r.x + r.w) * TILE - 18, (r.y + WALL_FACE_ROWS) * TILE + 4)
  }
}
