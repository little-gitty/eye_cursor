import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const { GITHUB_ACTIONS } = loadEnv(mode, '.', 'GITHUB_ACTIONS')

  return {
    base: GITHUB_ACTIONS === 'true' ? '/eye_cursor/' : '/',
    plugins: [react()],
    server: {
      host: '0.0.0.0',
      port: 5173,
    },
  }
})
