<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { RunEvent, Task } from '../api/types'
import { ROLE, TASK_STATE } from '../model/labels'
import {
  alongWall, bubbleFor, ELEVATOR_AT, flashFor, FLOOR_H, FLOOR_ITEMS, FLOOR_W, ISO_ZONES, placeSeats, PLANTS, project, RUGS, SHORT_PANES, WALL_PANES,
} from '../office/iso'
import type { ZoneId } from '../office/layout'

/**
 * 등각 사무실 한 층(사용자 디자인 지시: 파스텔 단면 평면도). 부모가 정한 크기에 맞춰 축소·확대한다.
 * 스냅샷 작업과 수신한 공개 사건만 보이고, 같은 정보는 SceneRoster(DOM 목록)로도 제공한다.
 * waiting: 사람의 결정을 기다리면 점선 실루엣으로 보인다(결정은 대화상자에서만 보낸다).
 */
const props = defineProps<{
  tasks: Task[]
  selectedTaskId: string | null
  motion: boolean
  subscribe: (fn: (event: RunEvent) => void) => () => void
  waiting?: { text: string; zone: ZoneId } | null
  /** 엘리베이터 칸이 이 층에 있으면 문이 열린다. floorLabel은 문 위 표시 */
  doorsOpen?: boolean
  floorLabel?: string
}>()
const emit = defineEmits<{ select: [taskId: string] }>()

const FLASH_MS = 6000
const FIT_MARGIN = 0.94
const GHOST_AT: Partial<Record<ZoneId, { px: number; py: number }>> = { meeting: { px: 56, py: 60 }, release: { px: 250, py: 860 } }

const wrap = ref<HTMLDivElement | null>(null)
const fit = ref({ s: 1, ox: 0, oy: 0 })
const prefersReduced = ref(false)
const hidden = ref(false)
const flashes = ref<Record<string, string>>({})
const animate = computed(() => props.motion && !prefersReduced.value && !hidden.value)

const placed = computed(() => placeSeats(props.tasks))
const tasksById = computed(() => new Map(props.tasks.map((t) => [t.id, t])))
const people = computed(() =>
  placed.value.seats
    .map((seat) => {
      const task = tasksById.value.get(seat.taskId)!
      const at = project(seat.px, seat.py)
      const flash = flashes.value[task.id]
      const state = bubbleFor(task)
      return {
        task,
        left: at.x - 16,
        top: at.y - 40,
        idle: task.state === 'pending' || task.state === 'ready',
        bubble: flash ? { text: flash, tone: 'active' } : state,
        label: `${ROLE[task.role].text} · ${task.title} · ${TASK_STATE[task.state].text}`,
      }
    })
    .sort((a, b) => a.top - b.top),
)
const zoneLabels = computed(() =>
  ISO_ZONES.map((z) => {
    const at = project(z.x + 22, z.y + z.h * 0.72)
    const more = placed.value.overflow[z.id]
    return { id: z.id, x: at.x, y: at.y, text: more ? `${z.label} · 외 ${more}명` : z.label }
  }),
)
const plants = PLANTS.map(([x, y]) => project(x, y))
const ghost = computed(() => {
  const w = props.waiting
  if (!w) return null
  const zone = ISO_ZONES.find((z) => z.id === w.zone)!
  const spot = GHOST_AT[w.zone] ?? { px: zone.x + zone.w / 2, py: zone.y + zone.h / 2 }
  const at = project(spot.px, spot.py)
  return { left: at.x - 16, top: at.y - 40, text: w.text }
})
const floorStyle = computed(() => ({ transform: `translate(${fit.value.ox}px, ${fit.value.oy}px) scale(${fit.value.s})` }))

function resize(): void {
  const box = wrap.value
  if (!box) return
  const w = box.clientWidth
  const h = box.clientHeight
  if (!w || !h) return
  const s = Math.min(w / FLOOR_W, h / FLOOR_H) * FIT_MARGIN
  fit.value = { s, ox: Math.round((w - FLOOR_W * s) / 2), oy: Math.round((h - FLOOR_H * s) / 2) }
}

const timers = new Set<ReturnType<typeof setTimeout>>()
function onEvent(event: RunEvent): void {
  const text = flashFor(event)
  const id = event.task_id
  if (!text || !id || !placed.value.seats.some((s) => s.taskId === id)) return
  flashes.value = { ...flashes.value, [id]: text }
  const timer = setTimeout(() => {
    timers.delete(timer)
    if (flashes.value[id] !== text) return
    const { [id]: _gone, ...rest } = flashes.value
    flashes.value = rest
  }, FLASH_MS)
  timers.add(timer)
}

let unsubscribe: (() => void) | null = null
let ro: ResizeObserver | null = null
let media: MediaQueryList | null = null
const onMedia = () => {
  prefersReduced.value = media?.matches ?? false
}
const onVisibility = () => {
  hidden.value = document.hidden
}

onMounted(() => {
  media = window.matchMedia?.('(prefers-reduced-motion: reduce)') ?? null
  onMedia()
  media?.addEventListener('change', onMedia)
  document.addEventListener('visibilitychange', onVisibility)
  ro = new ResizeObserver(resize)
  if (wrap.value) ro.observe(wrap.value)
  resize()
  unsubscribe = props.subscribe(onEvent)
})

onBeforeUnmount(() => {
  unsubscribe?.()
  ro?.disconnect()
  media?.removeEventListener('change', onMedia)
  document.removeEventListener('visibilitychange', onVisibility)
  timers.forEach(clearTimeout)
})
</script>

<template>
  <div ref="wrap" class="stage" :class="{ animate }">
    <div class="floor" :style="floorStyle">
      <div class="face-s wall short" aria-hidden="true">
        <span v-for="([x, len], i) in SHORT_PANES" :key="i" class="pane win" :style="{ left: `${alongWall(x)}px`, width: `${alongWall(len)}px` }" />
        <span class="elevator" :class="{ open: doorsOpen }" :style="{ left: `${alongWall(ELEVATOR_AT[0])}px`, width: `${alongWall(ELEVATOR_AT[1])}px` }">
          <span class="ele-display">{{ floorLabel ?? '' }}</span>
          <span class="leaf left" /><span class="leaf right" />
        </span>
      </div>
      <div class="face-l wall long" aria-hidden="true">
        <span v-for="([y, len, kind], i) in WALL_PANES" :key="i" :class="['pane', kind]" :style="{ left: `${alongWall(y)}px`, width: `${alongWall(len)}px` }" />
      </div>

      <div class="iso plate" aria-hidden="true">
        <div v-for="z in ISO_ZONES" :key="z.id" class="zone" :style="{ left: `${z.x}px`, top: `${z.y}px`, width: `${z.w}px`, height: `${z.h}px`, background: z.tone }" />
        <div
          v-for="(r, i) in RUGS"
          :key="`rug-${i}`"
          class="zone"
          :style="{ left: `${r.x}px`, top: `${r.y}px`, width: `${r.w}px`, height: `${r.h}px`, background: `var(--iso-${r.paint})`, borderRadius: r.round ? '50%' : '18px' }"
        />
        <div
          v-for="(it, i) in FLOOR_ITEMS"
          :key="i"
          :class="['solid', it.cls]"
          :style="{ left: `${it.x}px`, top: `${it.y}px`, width: `${it.w}px`, height: `${it.h}px`, background: `var(--iso-${it.paint})`, color: `var(--iso-${it.paint}-side)`, borderRadius: it.round ? '50%' : undefined }"
        />
      </div>

      <span v-for="z in zoneLabels" :key="z.id" class="zone-label" :style="{ left: `${z.x}px`, top: `${z.y}px` }">{{ z.text }}</span>
      <span v-for="(p, i) in plants" :key="i" class="plant" aria-hidden="true" :style="{ left: `${p.x - 14}px`, top: `${p.y - 38}px` }"><i /><i /><i /><b /></span>

      <div v-if="ghost" class="ghost" :style="{ left: `${ghost.left}px`, top: `${ghost.top}px` }">
        <span class="bubble wait"><span class="dot" aria-hidden="true" />{{ ghost.text }}</span>
        <span class="feet" aria-hidden="true" /><span class="body" aria-hidden="true" /><span class="head" aria-hidden="true" />
      </div>

      <button
        v-for="p in people"
        :key="p.task.id"
        type="button"
        class="person"
        :class="{ idle: p.idle }"
        :style="{ left: `${p.left}px`, top: `${p.top}px` }"
        :aria-label="p.label"
        :aria-pressed="p.task.id === selectedTaskId"
        @click="emit('select', p.task.id)"
      >
        <span v-if="p.bubble" :class="['bubble', `tone-${p.bubble.tone}`]"><span class="dot" aria-hidden="true" />{{ p.bubble.text }}</span>
        <span class="feet" aria-hidden="true" />
        <span class="body" aria-hidden="true" :style="{ background: p.idle ? 'var(--iso-idle-body)' : `var(--iso-role-${p.task.role})` }" />
        <span class="head" aria-hidden="true" />
        <span class="tag" aria-hidden="true">{{ p.task.title }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.stage { position: absolute; inset: 0; overflow: hidden; background: var(--iso-bg); }
.floor { position: absolute; left: 0; top: 0; width: 960px; height: 580px; transform-origin: 0 0; }

/* 등각 평면: 평면 요소를 눕혀 돌린다. 입체감은 currentColor 그림자를 겹쳐 만든다 */
.iso { position: absolute; transform: rotateX(60deg) rotateZ(-45deg); }
.plate { left: 280px; top: -140px; width: 400px; height: 900px; background: var(--iso-plate); color: var(--iso-slab-side); box-shadow: -2px 2px 0, -4px 4px 0, -6px 6px 0, -8px 8px 0, -10px 10px 0, -12px 12px 0, -14px 14px 0, -16px 16px 0, -18px 18px 0, -20px 20px 0 var(--iso-slab-edge); }
.zone, .solid { position: absolute; border-radius: 2px; }
.e8 { transform: translate(8px, -8px); box-shadow: -2px 2px 0, -4px 4px 0, -6px 6px 0, -8px 8px 0; }
.e12 { transform: translate(12px, -12px); box-shadow: -2px 2px 0, -4px 4px 0, -6px 6px 0, -8px 8px 0, -10px 10px 0, -12px 12px 0; }
.e20 { transform: translate(20px, -20px); box-shadow: -2px 2px 0, -4px 4px 0, -6px 6px 0, -8px 8px 0, -10px 10px 0, -12px 12px 0, -14px 14px 0, -16px 16px 0, -18px 18px 0, -20px 20px 0; }
.e44 { transform: translate(44px, -44px); box-shadow: -4px 4px 0, -8px 8px 0, -12px 12px 0, -16px 16px 0, -20px 20px 0, -24px 24px 0, -28px 28px 0, -32px 32px 0, -36px 36px 0, -40px 40px 0, -44px 44px 0; }
.e30 { transform: translate(30px, -30px); box-shadow: -3px 3px 0, -6px 6px 0, -9px 9px 0, -12px 12px 0, -15px 15px 0, -18px 18px 0, -21px 21px 0, -24px 24px 0, -27px 27px 0, -30px 30px 0; }
.e56 { transform: translate(56px, -56px); box-shadow: -4px 4px 0, -8px 8px 0, -12px 12px 0, -16px 16px 0, -20px 20px 0, -24px 24px 0, -28px 28px 0, -32px 32px 0, -36px 36px 0, -40px 40px 0, -44px 44px 0, -48px 48px 0, -52px 52px 0, -56px 56px 0; }
.part { box-shadow: 3px -3px 0, 6px -6px 0, 9px -9px 0, 12px -12px 0, 15px -15px 0, 18px -18px 0, 21px -21px 0, 24px -24px 0, 27px -27px 0, 30px -30px 0 var(--iso-wall-cap); }

/* 엘리베이터 문: 칸이 있는 층만 열린다 */
.elevator { position: absolute; top: 4px; bottom: 0; box-sizing: border-box; border: 3px solid var(--iso-steel-frame); border-bottom: 0; border-radius: 4px 4px 0 0; overflow: hidden; background: var(--iso-cab-light); }
.ele-display { position: absolute; left: 50%; top: 2px; transform: translateX(-50%); z-index: 1; padding: 0 6px; border-radius: 3px; background: #1f2233; color: #ffb347; font: 700 9px/14px var(--mono); }
.leaf { position: absolute; top: 18px; bottom: 0; width: 50%; background: var(--iso-steel); box-shadow: inset 0 0 0 1px var(--iso-steel-frame); transition: transform 520ms cubic-bezier(0.45, 0, 0.2, 1) 180ms; }
.leaf.left { left: 0; }
.leaf.right { right: 0; }
.elevator.open .leaf.left { transform: translateX(-82%); }
.elevator.open .leaf.right { transform: translateX(82%); }
@media (prefers-reduced-motion: reduce) { .leaf { transition: none; } }

/* 뒤쪽 벽 두 면(앞 벽은 걷어 내부를 보인다) */
.wall { position: absolute; height: 70px; box-sizing: border-box; transform-origin: 0 0; border-top: 4px solid var(--iso-wall-cap); }
.short { left: 20.4px; top: 151.6px; width: 282.8px; background: var(--iso-wall-short); transform: skewY(-26.565deg); }
.long { left: 303.2px; top: 10.2px; width: 636.4px; background: var(--iso-wall-long); transform: skewY(26.565deg); }
.pane { position: absolute; top: 12px; height: 40px; box-sizing: border-box; border-radius: 4px; border: 3px solid var(--iso-frame); }
.pane.win { background: linear-gradient(180deg, var(--iso-sky) 0 56%, var(--iso-hill) 56% 70%, var(--iso-sea) 70%); }
.pane.whiteboard { top: 10px; height: 46px; border-color: var(--iso-board-frame); background:
  linear-gradient(#f7d77a, #f7d77a) 12px 8px / 16px 12px no-repeat, linear-gradient(#f5a996, #f5a996) 34px 10px / 16px 12px no-repeat,
  linear-gradient(#a8dcc0, #a8dcc0) 56px 8px / 16px 12px no-repeat, linear-gradient(#a6c3ec, #a6c3ec) 22px 26px / 16px 12px no-repeat,
  var(--iso-board); }

.zone-label { position: absolute; transform: translate(-50%, -50%); white-space: nowrap; font-size: 12px; font-weight: 600; color: var(--iso-label); pointer-events: none; }

.plant { position: absolute; width: 28px; height: 40px; pointer-events: none; }
.plant i { position: absolute; top: 5px; width: 13px; height: 20px; border-radius: 50%; background: var(--iso-leaf); }
.plant i:nth-child(1) { left: 1px; transform: rotate(-26deg); }
.plant i:nth-child(2) { left: 14px; transform: rotate(26deg); background: var(--iso-leaf-2); }
.plant i:nth-child(3) { left: 8px; top: 0; width: 12px; height: 24px; background: var(--iso-leaf-3); }
.plant b { position: absolute; left: 7px; top: 23px; width: 14px; height: 14px; box-sizing: border-box; border-radius: 2px 2px 4px 4px; background: var(--iso-pot); border: 1px solid var(--iso-pot-line); }

/* 사람: 머리 테두리 + 파스텔 몸, 아래 이름표, 위 말풍선 */
.person, .ghost { position: absolute; width: 32px; height: 44px; padding: 0; border: 0; background: none; font: inherit; color: var(--iso-ink); }
.person { cursor: pointer; }
.person.idle .head, .person.idle .body { opacity: 0.75; }
.person.idle .head { border-color: var(--iso-idle-line); }
.head, .body, .feet { position: absolute; display: block; box-sizing: border-box; }
.head { left: 8px; top: 0; width: 16px; height: 16px; border-radius: 50%; background: var(--iso-head); border: 3px solid var(--iso-line); }
.body { left: 3px; top: 14px; width: 26px; height: 22px; border-radius: 13px 13px 6px 6px; }
.feet { left: 2px; top: 34px; width: 28px; height: 8px; border-radius: 50%; background: var(--iso-feet); }
.ghost .head { background: transparent; border: 2px dashed var(--tone-warn); }
.ghost .body { background: var(--iso-ghost-body); border: 2px dashed var(--tone-warn); }
.person[aria-pressed="true"] .feet { background: none; border: 3px solid var(--tone-warn); top: 32px; height: 12px; }
.person:focus-visible { outline: 3px solid var(--focus); outline-offset: 4px; border-radius: 8px; }

.tag, .bubble { position: absolute; left: 16px; display: flex; align-items: center; gap: 5px; white-space: nowrap; font-size: 11px; font-weight: 600; border-radius: 999px; pointer-events: none; }
.tag { top: 46px; transform: translateX(-50%); max-width: 130px; overflow: hidden; text-overflow: ellipsis; display: none; padding: 3px 9px; background: var(--iso-tag); color: var(--iso-ink); box-shadow: 0 1px 5px var(--iso-shadow); }
/* 이름표는 선택·포커스·마우스를 올린 사람만(겹침 방지). 상태 말풍선은 항상 보인다 */
.person:hover .tag, .person:focus-visible .tag, .person[aria-pressed="true"] .tag { display: block; z-index: 1; }
.person:hover, .person:focus-visible, .person[aria-pressed="true"] { z-index: 2; }
.person[aria-pressed="true"] .tag { outline: 2px solid var(--tone-warn); }
.bubble { bottom: 50px; transform: translateX(-50%); padding: 4px 10px; background: var(--iso-tag); color: var(--iso-ink); box-shadow: 0 2px 8px var(--iso-shadow); }
.bubble .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--tone-neutral); }
.bubble.tone-active .dot { background: var(--tone-ok); }
.bubble.tone-ok .dot { background: var(--tone-neutral); }
.bubble.tone-danger { color: var(--tone-danger); }
.bubble.tone-danger .dot { background: var(--tone-danger); }
.bubble.wait { background: var(--iso-wait-bg); color: var(--iso-wait-ink); }
.bubble.wait .dot { background: var(--tone-warn); }

.animate .bubble { animation: pop 260ms ease-out; }
.animate .bubble.tone-active .dot, .animate .bubble.wait .dot { animation: pulse 1.4s ease-in-out infinite; }
@keyframes pop { from { opacity: 0; transform: translate(-50%, 4px); } to { opacity: 1; transform: translate(-50%, 0); } }
@keyframes pulse { 50% { opacity: 0.35; } }
@media (prefers-reduced-motion: reduce) { .animate .bubble, .animate .bubble .dot { animation: none; } }
</style>
