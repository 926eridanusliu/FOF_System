import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const backendProxy = {
  '/api': 'http://127.0.0.1:8000',
  '/health': 'http://127.0.0.1:8000',
}

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: backendProxy,
  },
  preview: {
    port: 4173,
    proxy: backendProxy,
  },
})
