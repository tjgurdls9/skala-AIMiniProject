<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { RunEvent, Task } from '../api/types'
import { drawScene, INTRO_MS, packetFor, PACKET_MS, readPalette, type Packet } from '../office/draw'
import { computeLayout, hitSeat, type OfficeLayout } from '../office/layout'

/**
 * 픽셀 사무실 장면. 부모가 정한 크기를 채운다(전체 화면 → 스크롤로 축소).
 * 수신한 공개 사건과 스냅샷만 그리고, 같은 정보는 SceneRoster(DOM)로도 제공한다.
 */
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

/** 첫 진입에 방마다 불이 켜지는 장식 인트로. 모션이 꺼져 있으면 바로 켜진 상태 */
let introStart = 0
const introProgress = (now: number) => (animate.value && introStart ? Math.min(1, (now - introStart) / INTRO_MS) : 1)

const tasksById = computed(() => new Map(props.tasks.map((t) => [t.id, t])))
const layout = computed<OfficeLayout>(() => computeLayout(size.value.w, size.value.h, props.tasks))
const animate = computed(() => props.motion && !prefersReduced.value && !hidden.value)

let timer: ReturnType<typeof setTimeout> | null = null
let raf = 0

function paint(now = performance.now()): void {
  const el = canvas.value
  if (!el || size.value.w === 0 || size.value.h === 0) return
  const ctx = el.getContext('2d')
  if (!ctx) return
  const dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR)
  const frame = animate.value ? Math.floor(now / TYPING_FRAME_MS) : 0
  drawScene(ctx, { layout: layout.value, tasks: tasksById.value, selectedTaskId: props.selectedTaskId, packets: packets.value, frame, now, intro: introProgress(now) }, readPalette(el), dpr)
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
  if (packets.value.length > 0 || introProgress(now) < 1) raf = requestAnimationFrame(schedule)
  else if (props.tasks.some((t) => t.state === 'running')) timer = setTimeout(schedule, TYPING_FRAME_MS)
}

function resize(): void {
  const el = canvas.value
  const box = wrap.value
  if (!el || !box) return
  const w = Math.floor(box.clientWidth)
  const h = Math.floor(box.clientHeight)
  if (w === size.value.w && h === size.value.h) return
  const dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR)
  el.width = Math.round(w * dpr)
  el.height = Math.round(h * dpr)
  size.value = { w, h }
  paint()
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
// 테마 전환(data-theme) 시 팔레트를 다시 읽어 그린다
const themeObserver = new MutationObserver(() => paint())

onMounted(() => {
  media = window.matchMedia('(prefers-reduced-motion: reduce)')
  onMedia()
  media.addEventListener('change', onMedia)
  document.addEventListener('visibilitychange', onVisibility)
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
  ro = new ResizeObserver(resize)
  if (wrap.value) ro.observe(wrap.value)
  resize()
  introStart = performance.now()
  schedule()
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
  themeObserver.disconnect()
  media?.removeEventListener('change', onMedia)
  document.removeEventListener('visibilitychange', onVisibility)
  if (timer) clearTimeout(timer)
  cancelAnimationFrame(raf)
})

watch([() => props.tasks, () => props.selectedTaskId, animate], schedule)
</script>

<template>
  <div ref="wrap" class="stage">
    <canvas ref="canvas" aria-hidden="true" @click="onCanvasClick" />
  </div>
</template>

<style scoped>
.stage { position: absolute; inset: 0; overflow: hidden; background: var(--px-void); }
canvas { display: block; width: 100%; height: 100%; cursor: pointer; }
</style>
