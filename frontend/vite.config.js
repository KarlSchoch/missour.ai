import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

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
    proxy: { '/api': 'http://localhost:8000/' },
  },
  build: {
    outDir: 'dist',
    // Write manifest at dist/manifest.json (not hidden) so Django collects it
    manifest: 'manifest.json',
    emptyOutDir: true,
    rollupOptions: {
      // Explicit multi-entry build so Django can load per-page bundles via django-vite
      input: {
        'src/analyze-audio-page-section.jsx': resolve(__dirname, 'src/analyze-audio-page-section.jsx'),
        'src/view-topics.jsx': resolve(__dirname, 'src/view-topics.jsx'),
        'src/view-transcript-chunk-page-section.jsx': resolve(__dirname, 'src/view-transcript-chunk-page-section.jsx'),
        'src/topic-selector.jsx': resolve(__dirname, 'src/topic-selector.jsx'),
      },
    },
  }
}))
