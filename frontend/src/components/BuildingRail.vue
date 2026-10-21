<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'

/**
 * 건물 엘리베이터(사용자 디자인 지시). 실행 하나가 건물이고 Sprint 하나가 층이다. 위층일수록 나중 단계.
 * 층 버튼을 누르면 칸이 그 층으로 움직이고, 표시창이 층과 방향을 보이며, 해당 층 단면으로 이동한다.
 */
export interface FloorEntry { id: string; num: string; title: string; sub: string; tone: 'ok' | 'active' | 'danger' | 'neutral' }

const props = defineProps<{ floors: FloorEntry[]; selectedId: string | null; currentId: string | null; motion: boolean }>()
const emit = defineEmits<{ select: [id: string] }>()

/** 칸 이동 시간(층당). 모션이 꺼져 있으면 바로 도착한다 */
const MS_PER_FLOOR = 180
const MAX_RIDE_MS = 900

const stop = computed(() => Math.max(0, props.floors.findIndex((f) => f.id === props.selectedId)))
const selected = computed(() => props.floors[stop.value] ?? null)
/** 목록은 위층부터라 인덱스가 줄면 올라간다 */
const direction = ref<'up' | 'down' | null>(null)
const rideMs = ref(0)
let arrive: ReturnType<typeof setTimeout> | null = null

watch(stop, (next, prev) => {
  if (prev === undefined || next === prev) return
  if (arrive) clearTimeout(arrive)
  direction.value = next < prev ? 'up' : 'down'
  rideMs.value = props.motion ? Math.min(MAX_RIDE_MS, Math.abs(next - prev) * MS_PER_FLOOR + 240) : 0
  arrive = setTimeout(() => {
    direction.value = null
  }, rideMs.value)
})
onBeforeUnmount(() => {
  if (arrive) clearTimeout(arrive)
})

function go(id: string): void {
  emit('select', id)
  document.getElementById(`floor-${id}`)?.scrollIntoView?.({ behavior: props.motion ? 'smooth' : 'auto', block: 'start' })
}
</script>

<template>
  <nav class="building-rail" aria-label="엘리베이터 · 층 이동">
    <div class="roof" aria-hidden="true"><span class="antenna" /><span class="sign">LIFECYCLE OFFICE</span></div>
    <p class="elevator-display" aria-live="polite">
      <span class="arrow" :class="{ lit: direction === 'up' }" aria-hidden="true">▲</span>
      <span class="level">{{ selected?.num ?? '–' }}</span>
      <span class="arrow" :class="{ lit: direction === 'down' }" aria-hidden="true">▼</span>
      <span class="sr-only">{{ direction === 'up' ? '올라가는 중' : direction === 'down' ? '내려가는 중' : '도착' }}</span>
    </p>
    <div class="shaft" :style="{ '--stop': stop, '--ride': `${rideMs}ms` }">
      <span class="cab" :style="{ '--stop': stop }" aria-hidden="true"><i /><i /></span>
      <a
        v-for="f in floors"
        :key="f.id"
        :href="`#floor-${f.id}`"
        class="rail-floor"
        :aria-current="f.id === selectedId"
        @click.prevent="go(f.id)"
      >
        <span class="floor-num">{{ f.num }}</span>
        <span class="text">
          <span class="name">{{ f.title }}</span>
          <span class="sub"><span :class="['dot', `tone-${f.tone}`]" aria-hidden="true" />{{ f.sub }}</span>
        </span>
        <span v-if="f.id === currentId" class="now">현재</span>
      </a>
    </div>
    <div class="ground" aria-hidden="true" />
    <p class="note">층 = Sprint · 위층일수록 나중 단계</p>
  </nav>
</template>

<style scoped>
.building-rail { --row: 64px; --row-gap: 8px; display: flex; flex-direction: column; gap: 10px; padding: 14px; border-radius: 18px; background: var(--surface); border: 1px solid var(--line); }
.roof { position: relative; display: flex; justify-content: center; padding-top: 14px; }
.antenna { position: absolute; top: 0; width: 2px; height: 14px; background: var(--tone-warn); }
.sign { width: 100%; padding: 11px 8px; text-align: center; font-size: 12px; font-weight: 700; letter-spacing: 0.08em; color: #fff; background: #4a4f9a; clip-path: polygon(7% 0, 93% 0, 100% 100%, 0 100%); }

/* 층 표시창: 엘리베이터 위 디지털 표시 */
.elevator-display {
  display: flex; align-items: center; justify-content: center; gap: 14px; margin: 0; padding: 8px 12px;
  border-radius: 12px; background: #1f2233; color: #ffb347; font-family: var(--mono); box-shadow: inset 0 0 0 2px #3a3f55;
}
.level { min-width: 3ch; text-align: center; font-size: 22px; font-weight: 700; letter-spacing: 0.04em; }
.arrow { font-size: 12px; color: #4a4f66; transition: color 160ms; }
.arrow.lit { color: #ffb347; }

/* 승강로: 칸이 고른 층 자리로 미끄러진다 */
.shaft { position: relative; display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--row-gap); padding: 4px; border-radius: 14px; background: repeating-linear-gradient(180deg, var(--surface-2) 0 2px, transparent 2px 12px); }
.cab {
  position: absolute; left: 4px; right: 4px; top: 4px; height: var(--row); z-index: 0; border-radius: 12px;
  background: #2f3370; border: 2px solid #f2a33a; box-sizing: border-box;
  transform: translateY(calc(var(--stop) * (var(--row) + var(--row-gap))));
  transition: transform var(--ride) cubic-bezier(0.45, 0, 0.2, 1);
}
.cab i { position: absolute; top: 6px; bottom: 6px; width: 2px; background: rgb(255 255 255 / 0.12); }
.cab i:first-child { left: 30%; }
.cab i:last-child { right: 30%; }
.rail-floor {
  position: relative; z-index: 1; display: flex; align-items: center; gap: 10px; min-width: 0; height: var(--row); padding: 8px 12px; box-sizing: border-box;
  border-radius: 12px; border: 1px solid var(--line); background: color-mix(in srgb, var(--surface) 92%, transparent); color: var(--ink); text-decoration: none;
  transition: background 160ms, color 160ms, border-color 160ms;
}
.rail-floor:hover { border-color: var(--ink-3); }
.rail-floor[aria-current="true"] { background: transparent; border-color: transparent; color: #fff; }
.rail-floor[aria-current="true"] .sub { color: #e7e8fb; }
.floor-num {
  flex: 0 0 auto; width: 30px; height: 30px; display: grid; place-items: center; border-radius: 50%;
  font-family: var(--mono); font-size: 12px; font-weight: 700; color: #4a4f9a; border: 2px solid currentColor; box-sizing: border-box;
}
.rail-floor[aria-current="true"] .floor-num { color: #ffb347; box-shadow: 0 0 8px rgb(255 179 71 / 0.6); }
.text { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.name { font-size: 13px; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sub { display: flex; align-items: center; gap: 5px; font-size: 11px; color: var(--ink-3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dot { width: 7px; height: 7px; border-radius: 50%; flex: 0 0 auto; background: var(--tone-neutral); }
.dot.tone-ok { background: var(--tone-ok); }
.dot.tone-active { background: var(--tone-active); }
.dot.tone-danger { background: var(--tone-danger); }
.now { margin-left: auto; flex: 0 0 auto; white-space: nowrap; font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 999px; background: #fff1dc; color: #7a4300; }
.ground { height: 6px; border-radius: 3px; background: #9fd3a4; }
.note { margin: 0; font-size: 11px; color: var(--ink-3); text-align: center; }

@media (prefers-reduced-motion: reduce) { .cab { transition: none; } }
/* 좁은 화면: 표시창 + 층 버튼 가로 줄(칸 대신 버튼 강조) */
@media (max-width: 1180px) {
  .building-rail { flex-direction: row; align-items: center; overflow-x: auto; padding: 10px; }
  .roof, .ground, .note, .cab { display: none; }
  .shaft { display: flex; background: none; padding: 0; }
  .rail-floor { flex: 0 0 auto; }
  .rail-floor[aria-current="true"] { background: #2f3370; border: 2px solid #f2a33a; }
}
</style>
