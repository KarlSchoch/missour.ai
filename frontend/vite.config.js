import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  // Align with Django template that references /static/ in dev
  base: '/static/',
  plugins: [
    {
      name: 'log-base',
      configResolved(config) {
        console.log(`[vite] mode=${config.mode} base=${config.base}`)
      },
    },
    react({ fastRefresh: false }),
  ],
  server: {
    port: 5173,
    proxy: { '/api': 'http://localhost:8000' },
  },
  build: {
    outDir: 'dist',
    manifest: true,
    emptyOutDir: true,
  }
}))
