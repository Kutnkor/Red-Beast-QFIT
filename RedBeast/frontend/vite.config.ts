/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const API = process.env.BLINKSPACE_API ?? 'http://127.0.0.1:8765'

// Production: FastAPI serves dist/ at "/" and the API under "/api" (same origin).
// Development: the dev server proxies "/api" to the backend.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': { target: API, changeOrigin: false } } },
  preview: { proxy: { '/api': { target: API, changeOrigin: false } } },
  build: { assetsInlineLimit: 0, sourcemap: false, rolldownOptions: { input: ['index.html', 'v4.html'] } },
  test: {
    environment: 'jsdom',
    include: ['src/tests/**/*.test.{ts,tsx}'],
    setupFiles: ['src/tests/setup.ts'],
    restoreMocks: true,
  },
})
