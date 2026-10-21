<script setup lang="ts">
import { computed } from 'vue'

/**
 * 건물 엘리베이터(사용자 디자인 지시: 컷 A). 실행 하나가 건물이고 Sprint 하나가 층이다. 위층일수록 나중 단계.
 * 층 수에 맞는 간결한 높이(층마다 한 칸)이고, 층 이름·상태는 접근 가능한 이름과 툴팁으로 준다.
 * 칸은 cabId, 표시창은 displayId·direction을 따른다. 진행 순서(문 닫힘·이동·열림)는 부모의 useElevator가 정한다.
 */
export interface FloorEntry { id: string; num: string; title: string; sub: string; tone: 'ok' | 'active' | 'danger' | 'neutral' }

const props = defineProps<{
  floors: FloorEntry[]
  /** 고른(가려는) 층 */
  selectedId: string | null
  currentId: string | null
  cabId: string | null
  displayId: string | null
  direction: 'up' | 'down' | null
  rideMs: number
}>()
const emit = defineEmits<{ select: [id: string] }>()

const stop = computed(() => Math.max(0, props.floors.findIndex((f) => f.id === props.cabId)))
const display = computed(() => props.floors.find((f) => f.id === props.displayId)?.num ?? '–')
const label = (f: FloorEntry): string => `${f.num} ${f.title} · ${f.sub}${f.id === props.currentId ? ' · 현재 Sprint' : ''}`
</script>

<template>
  <nav class="building-rail" aria-label="엘리베이터 · 층 이동">
    <p class="elevator-display" aria-live="polite">
      <span class="arrow" :class="{ lit: direction === 'up' }" aria-hidden="true">▲</span>
      <span class="level">{{ display }}</span>
      <span class="arrow" :class="{ lit: direction === 'down' }" aria-hidden="true">▼</span>
      <span class="sr-only">{{ direction === 'up' ? '올라가는 중' : direction === 'down' ? '내려가는 중' : '도착' }}</span>
    </p>
    <div class="shaft" :style="{ '--ride': `${rideMs}ms` }">
      <span class="cab" :style="{ '--stop': stop }" aria-hidden="true" />
      <a
        v-for="f in floors"
        :key="f.id"
        :href="`#floor-${f.id}`"
        class="rail-floor"
        :aria-current="f.id === selectedId"
        :aria-label="label(f)"
        :title="label(f)"
        @click.prevent="emit('select', f.id)"
      >
        <span class="floor-num">{{ f.num }}</span>
        <span :class="['dot', `tone-${f.tone}`]" aria-hidden="true" />
        <span v-if="f.id === currentId" class="now" aria-hidden="true" />
      </a>
    </div>
  </nav>
</template>

<style scoped>
.building-rail {
  --row: 44px; --row-gap: 6px; width: 96px; box-sizing: border-box; display: flex; flex-direction: column; gap: 8px; padding: 8px;
  border-radius: 18px; background: color-mix(in srgb, var(--surface) 94%, transparent); border: 1px solid var(--line); box-shadow: 0 4px 16px var(--iso-shadow);
}
.elevator-display {
  display: flex; align-items: center; justify-content: center; gap: 6px; margin: 0; padding: 6px 8px;
  border-radius: 10px; background: #1f2233; color: #ffb347; font-family: var(--mono); box-shadow: inset 0 0 0 2px #3a3f55;
}
.level { min-width: 2.4ch; text-align: center; font-size: 18px; font-weight: 700; }
.arrow { font-size: 10px; color: #4a4f66; transition: color 160ms; }
.arrow.lit { color: #ffb347; }

/* 승강로: 칸이 층 칸을 따라 미끄러진다 */
.shaft { position: relative; display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--row-gap); padding: 4px; border-radius: 12px; background: repeating-linear-gradient(180deg, var(--surface-2) 0 2px, transparent 2px 12px); }
.cab {
  position: absolute; left: 4px; right: 4px; top: 4px; height: var(--row); z-index: 0; border-radius: 10px;
  background: #2f3370; border: 2px solid #f2a33a; box-sizing: border-box;
  transform: translateY(calc(var(--stop) * (var(--row) + var(--row-gap))));
  transition: transform var(--ride) cubic-bezier(0.45, 0, 0.2, 1);
}
.rail-floor {
  position: relative; z-index: 1; display: flex; align-items: center; justify-content: center; gap: 6px; min-width: 0; height: var(--row); box-sizing: border-box;
  border-radius: 10px; border: 1px solid var(--line); background: color-mix(in srgb, var(--surface) 92%, transparent); color: var(--ink); text-decoration: none;
  transition: background 160ms, color 160ms, border-color 160ms;
}
.rail-floor:hover { border-color: var(--ink-3); }
.rail-floor:focus-visible { outline: 3px solid var(--focus); outline-offset: 2px; }
.rail-floor[aria-current="true"] { background: transparent; border-color: transparent; color: #fff; }
.floor-num { font-family: var(--mono); font-size: 14px; font-weight: 700; color: #4a4f9a; }
.rail-floor[aria-current="true"] .floor-num { color: #ffb347; }
.dot { width: 7px; height: 7px; border-radius: 50%; flex: 0 0 auto; background: var(--tone-neutral); }
.dot.tone-ok { background: var(--tone-ok); }
.dot.tone-active { background: var(--tone-active); }
.dot.tone-danger { background: var(--tone-danger); }
.now { position: absolute; right: 5px; top: 5px; width: 7px; height: 7px; border-radius: 50%; box-sizing: border-box; border: 2px solid #f2a33a; background: #fff1dc; }

@media (prefers-reduced-motion: reduce) { .cab { transition: none; } }
/* 좁은 화면: 가로 줄(칸 대신 선택 강조) */
@media (max-width: 860px) {
  .building-rail { width: auto; flex-direction: row; align-items: center; overflow-x: auto; }
  .cab { display: none; }
  .shaft { display: flex; background: none; padding: 0; }
  .rail-floor { flex: 0 0 auto; min-width: 56px; padding: 0 8px; }
  .rail-floor[aria-current="true"] { background: #2f3370; border: 2px solid #f2a33a; }
}
</style>
