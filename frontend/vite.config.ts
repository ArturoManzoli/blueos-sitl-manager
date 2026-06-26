import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vuetify, { transformAssetUrls } from 'vite-plugin-vuetify'

export default defineConfig({
  // Relative base so the build also works when served under /extensionv2/<name>/.
  base: './',
  plugins: [
    vue({ template: { transformAssetUrls } }),
    vuetify({ autoImport: true }),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    outDir: 'dist',
  },
  server: {
    port: 8080,
    proxy: {
      // Local dev: forward API calls to a running backend.
      '/v1.0': 'http://localhost:8000',
      '/latest': 'http://localhost:8000',
      '/register_service': 'http://localhost:8000',
    },
  },
})
