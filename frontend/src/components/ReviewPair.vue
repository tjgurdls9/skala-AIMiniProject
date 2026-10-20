<script setup lang="ts">
import type { ReviewPair } from '../model/derive'
import { shortDigest, VERDICT } from '../model/labels'

/** 검증·보안 보고서를 나란히, 각자의 판정으로 보여준다. 둘을 하나의 PASS로 합치지 않는다. */
defineProps<{ pair: ReviewPair }>()
const emit = defineEmits<{ artifact: [id: string] }>()
</script>

<template>
  <div class="pair">
    <article v-for="[role, label] in ([['validator', '검증'], ['security', '보안']] as const)" :key="role" class="report">
      <h4>{{ label }} 보고서</h4>
      <template v-if="pair[role]">
        <p :class="['tone', `tone-${VERDICT[pair[role]!.verdict].tone}`]">
          {{ VERDICT[pair[role]!.verdict].glyph }} {{ VERDICT[pair[role]!.verdict].text }}
        </p>
        <dl class="kv small">
          <dt>커밋</dt><dd><code>{{ shortDigest(pair[role]!.commit_sha) }}</code></dd>
          <dt>이미지</dt><dd><code>{{ shortDigest(pair[role]!.image_digest) }}</code></dd>
          <dt>명세</dt><dd><code>{{ pair[role]!.spec_version_id }}</code></dd>
          <dt>원본 해시</dt><dd><code>{{ shortDigest(pair[role]!.content_digest) }}</code></dd>
        </dl>
        <button type="button" class="btn small" @click="emit('artifact', pair[role]!.artifact_id)">원본 보고서 보기</button>
      </template>
      <p v-else class="tone tone-warn">– 아직 제출되지 않음</p>
    </article>
  </div>
</template>

<style scoped>
.pair { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; }
.report { border: 1px solid var(--line); border-radius: var(--radius); padding: 10px; display: grid; gap: 6px; align-content: start; }
h4 { font-size: 0.9rem; }
</style>
