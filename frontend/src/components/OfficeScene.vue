<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { RunEvent, Task } from '../api/types'
import { ROLE, TASK_STATE } from '../model/labels'
import { drawScene, packetFor, PACKET_MS, readPalette, type Packet } from '../office/draw'
import { computeLayout, hitSeat, ROLE_ZONE, ZONE_LABEL, type OfficeLayout, type ZoneId } from '../office/layout'

const props = defineProps<{
  tasks: Task[]
  selectedTaskId: string | null
  motion: boolean
  subscribe: (fn: (event: RunEvent) => void) => () => void
}>()
const emit = defineEmits<{ select: [taskId: string] }>()

const TYPING_FRAME_MS = 280
const MAX_PACKETS = 6
const MAX_DPR = 2

const wrap = ref<HTMLDivElement | null>(null)
const canvas = ref<HTMLCanvasElement | null>(null)
const size = ref({ w: 0, h: 0 })
const packets = ref<Packet[]>([])
const prefersReduced = ref(false)
const hidden = ref(false)

const tasksById = computed(() => new Map(props.tasks.map((t) => [t.id, t])))
const layout = computed<OfficeLayout>(() => computeLayout(size.value.w, size.value.h, props.tasks))
const animate = computed(() => props.motion && !prefersReduced.value && !hidden.value)

const roster = computed(() => {
  const order: ZoneId[] = ['meeting', 'build', 'validate', 'security', 'release']
  return order.map((zone) => ({ zone, label: ZONE_LABEL[zone], tasks: props.tasks.filter((t) => ROLE_ZONE[t.role] === zone && t.state !== 'superseded') }))
})

let timer: ReturnType<typeof setTimeout> | null = null
let raf = 0

function paint(now = performance.now()): void {
  const el = canvas.value
  if (!el || size.value.w === 0) return
  const ctx = el.getContext('2d')
  if (!ctx) return
  const dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR)
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  const frame = animate.value ? Math.floor(now / TYPING_FRAME_MS) : 0
  drawScene(ctx, { layout: layout.value, tasks: tasksById.value, selectedTaskId: props.selectedTaskId, packets: packets.value, frame, now }, readPalette(el))
}

/** 실행 중 작업이 있으면 낮은 빈도로, 패킷이 있으면 rAF로 그린다. 그 외에는 변경 시에만 그린다. */
function schedule(): void {
  if (timer) clearTimeout(timer)
  cancelAnimationFrame(raf)
  timer = null
  if (!animate.value) {
    packets.value = []
    paint()
    return
  }
  const now = performance.now()
  packets.value = packets.value.filter((p) => now - p.startedAt < PACKET_MS)
  paint(now)
  if (packets.value.length > 0) raf = requestAnimationFrame(schedule)
  else if (props.tasks.some((t) => t.state === 'running')) timer = setTimeout(schedule, TYPING_FRAME_MS)
}

function resize(): void {
  const el = canvas.value
  const box = wrap.value
  if (!el || !box) return
  const w = Math.floor(box.clientWidth)
  const h = w < 560 ? 340 : Math.max(300, Math.min(400, Math.round(w * 0.36)))
  const dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR)
  el.width = Math.round(w * dpr)
  el.height = Math.round(h * dpr)
  el.style.height = `${h}px`
  size.value = { w, h }
  schedule()
}

function onCanvasClick(e: MouseEvent): void {
  const el = canvas.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const id = hitSeat(layout.value, e.clientX - rect.left, e.clientY - rect.top)
  if (id) emit('select', id)
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
  media = window.matchMedia('(prefers-reduced-motion: reduce)')
  onMedia()
  media.addEventListener('change', onMedia)
  document.addEventListener('visibilitychange', onVisibility)
  ro = new ResizeObserver(resize)
  if (wrap.value) ro.observe(wrap.value)
  resize()
  unsubscribe = props.subscribe((event) => {
    if (!animate.value) return
    const packet = packetFor(event, layout.value, tasksById.value, performance.now())
    if (!packet) return
    packets.value = [...packets.value, packet].slice(-MAX_PACKETS)
    schedule()
  })
})

onBeforeUnmount(() => {
  unsubscribe?.()
  ro?.disconnect()
  media?.removeEventListener('change', onMedia)
  document.removeEventListener('visibilitychange', onVisibility)
  if (timer) clearTimeout(timer)
  cancelAnimationFrame(raf)
})

watch([() => props.tasks, () => props.selectedTaskId, animate], schedule)
// 테마 전환(data-theme) 시 팔레트를 다시 읽어 그린다
const themeObserver = new MutationObserver(() => paint())
onMounted(() => themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] }))
onBeforeUnmount(() => themeObserver.disconnect())
</script>

<template>
  <section class="office" aria-labelledby="office-title">
    <h2 id="office-title" class="sr-only">사무실 장면</h2>
    <div ref="wrap" class="stage">
      <canvas ref="canvas" aria-hidden="true" @click="onCanvasClick" />
    </div>
    <p class="legend small muted">
      장면은 수신한 공개 사건과 스냅샷만 표시합니다. 움직임은 연출이며 진행·성공의 근거가 아닙니다.
      <template v-if="!animate">모션 꺼짐 — 정적 장면.</template>
    </p>
    <div class="roster" aria-label="장면의 작업 목록 (장면과 같은 내용)">
      <div v-for="group in roster" :key="group.zone" class="zone">
        <h3>{{ group.label }}</h3>
        <p v-if="group.tasks.length === 0" class="small muted">이 Sprint 작업 없음</p>
        <ul class="plain">
          <li v-for="t in group.tasks" :key="t.id">
            <button
              type="button"
              class="seat"
              :aria-pressed="t.id === selectedTaskId"
              @click="emit('select', t.id)"
            >
              <span class="role" :data-role="t.role">{{ ROLE[t.role].glyph }}<span class="sr-only">{{ ROLE[t.role].text }}</span></span>
              <span class="title">{{ t.title }}</span>
              <span :class="['tone', `tone-${TASK_STATE[t.state].tone}`, 'small']">{{ TASK_STATE[t.state].glyph }} {{ TASK_STATE[t.state].text }}</span>
            </button>
          </li>
        </ul>
      </div>
    </div>
  </section>
</template>

<style scoped>
.office { display: grid; gap: 8px; }
.stage { width: 100%; border-radius: var(--radius); overflow: hidden; border: 1px solid var(--line); }
canvas { display: block; width: 100%; cursor: pointer; }
.legend { margin: 0; }
.roster { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 8px 12px; }
.zone h3 { font-size: 0.8rem; color: var(--ink-3); font-weight: 600; margin-bottom: 4px; }
.seat {
  width: 100%; min-height: var(--tap); display: grid; grid-template-columns: auto 1fr; gap: 0 8px; align-items: center;
  padding: 6px 8px; text-align: left; border: 1px solid var(--line); border-radius: var(--radius); background: var(--surface); cursor: pointer;
}
.seat:hover { background: var(--surface-2); }
.seat[aria-pressed="true"] { border-color: var(--focus); box-shadow: inset 0 0 0 1px var(--focus); }
.seat .role {
  grid-row: span 2; width: 26px; height: 26px; border-radius: 6px; display: grid; place-items: center;
  font-weight: 700; font-size: 0.8rem; color: var(--surface);
}
.seat .title { font-size: 0.9rem; line-height: 1.3; }
.role[data-role="planner"] { background: var(--role-planner); }
.role[data-role="supervisor"] { background: var(--role-supervisor); }
.role[data-role="builder"] { background: var(--role-builder); }
.role[data-role="validator"] { background: var(--role-validator); }
.role[data-role="security"] { background: var(--role-security); }
.role[data-role="release"] { background: var(--role-release); }
</style>
