import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

// 포트·프록시는 Codex 인계(D1 계약 §7) 기준: 프론트 127.0.0.1:5173, API 127.0.0.1:8000
export default defineConfig({
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false } },
  },
  test: {
    environment: 'happy-dom',
    include: ['tests/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,vue}'],
      exclude: ['src/generated/**', 'src/main.ts', 'src/env.d.ts'],
    },
  },
})
