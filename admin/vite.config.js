import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [react()],
  base: '/admin-ui/',
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      // 공개 랜딩이 실제 위젯 ChatWidget을 재사용(mock 트랜스포트로 구동). 위젯 빌드는 무관.
      '@widget': fileURLToPath(new URL('../widget/src', import.meta.url)),
    },
  },
  build: {
    outDir: 'dist',
    // 멀티페이지: admin SPA(index.html, /admin-ui/) + 공개 랜딩(landing.html, nginx가 /에 서빙).
    rollupOptions: {
      input: {
        main: fileURLToPath(new URL('./index.html', import.meta.url)),
        landing: fileURLToPath(new URL('./landing.html', import.meta.url)),
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/setupTests.js',
  },
  server: {
    port: 5174,
    host: '0.0.0.0',
    allowedHosts: true,
    proxy: {
      '/api': {
        target: process.env.VITE_PROXY_TARGET || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
