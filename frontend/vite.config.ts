import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  // The backend only allows browser requests from localhost:5173 / 127.0.0.1:5173 (CORS),
  // so fail loudly instead of silently moving to another port.
  server: { port: 5173, strictPort: true },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
  },
})
