<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { drawStatic, readPalette } from '../office/draw'
import { chooseMap, TILE } from '../office/layout'

/** 시작 화면 바닥에 희미하게 깔리는 빈 사무실(장식). 입력 후 이 사무실이 화면을 채운다 */
const canvas = ref<HTMLCanvasElement | null>(null)

onMounted(() => {
  const el = canvas.value
  const ctx = el?.getContext('2d')
  if (!el || !ctx) return
  const { map } = chooseMap(1600, 900)
  el.width = map.w * TILE
  el.height = map.h * TILE
  drawStatic(ctx, map, readPalette(el))
})
</script>

<template>
  <canvas ref="canvas" class="silhouette" aria-hidden="true" />
</template>

<style scoped>
.silhouette {
  position: absolute;
  left: 50%;
  bottom: -18vh;
  width: min(1100px, 130vw);
  transform: translateX(-50%) perspective(900px) rotateX(38deg);
  transform-origin: 50% 100%;
  image-rendering: pixelated;
  opacity: 0.32;
  filter: saturate(0.9);
  -webkit-mask-image: linear-gradient(to top, transparent 0%, #000 35%, #000 55%, transparent 100%);
  mask-image: linear-gradient(to top, transparent 0%, #000 35%, #000 55%, transparent 100%);
  pointer-events: none;
}
</style>
