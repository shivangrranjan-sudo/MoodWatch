import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// During `npm run dev`, forward API requests to the FastAPI backend
// (uvicorn on :8000). The background image is served locally from public/static
// so it never depends on the proxy.
const backend = 'http://127.0.0.1:8000'
const proxy = (path) => ({ [path]: { target: backend, changeOrigin: true } })

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      ...proxy('/search-full'),
      ...proxy('/feedback'),
      ...proxy('/trailer'),
      ...proxy('/dashboard'),
      ...proxy('/ping'),
    },
  },
})
