<script setup lang="ts">
import { computed } from 'vue'
import type { Task } from '../api/types'
import { ROLE, TASK_STATE } from '../model/labels'
import { ROLE_ZONE, ZONE_LABEL, type ZoneId } from '../office/layout'

/** 사무실 장면과 같은 내용을 DOM으로(키보드·스크린리더·장면에 못 놓은 작업 포함) */
const props = defineProps<{ tasks: Task[]; selectedTaskId: string | null }>()
const emit = defineEmits<{ select: [taskId: string] }>()

const ORDER: ZoneId[] = ['meeting', 'build', 'validate', 'security', 'release']
const groups = computed(() =>
  ORDER.map((zone) => ({ zone, label: ZONE_LABEL[zone], tasks: props.tasks.filter((t) => ROLE_ZONE[t.role] === zone && t.state !== 'superseded') })),
)
</script>

<template>
  <section class="roster panel" aria-labelledby="roster-title">
    <header>
      <h2 id="roster-title">사무실 좌석</h2>
      <span class="small muted">장면과 같은 내용 · 움직임은 연출이며 진행·성공의 근거가 아님</span>
    </header>
    <div class="zones">
      <div v-for="group in groups" :key="group.zone" class="zone">
        <h3>{{ group.label }}</h3>
        <p v-if="group.tasks.length === 0" class="small muted">이 Sprint 작업 없음</p>
        <ul class="plain">
          <li v-for="t in group.tasks" :key="t.id">
            <button type="button" class="seat" :aria-pressed="t.id === selectedTaskId" @click="emit('select', t.id)">
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
.zones { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 8px 12px; }
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
