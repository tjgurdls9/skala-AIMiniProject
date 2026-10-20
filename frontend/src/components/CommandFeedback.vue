<script setup lang="ts">
import { ApiError, errorHint } from '../api/errors'

/** 명령 실패를 원인·다음 행동과 함께 보여준다. 입력은 지우지 않는다. */
defineProps<{ error: ApiError | null }>()
</script>

<template>
  <div v-if="error" class="error-box" role="alert">
    <strong>{{ error.code === 'EXAMPLE_NOOP' ? '보내지 않음' : '처리되지 않음' }}</strong> — {{ error.message }}
    <p class="small">{{ errorHint(error) }}</p>
  </div>
</template>
