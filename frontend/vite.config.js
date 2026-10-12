import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// Configuración de Vite para TTR_
// - En desarrollo, todo lo que empiece con /api se reenvía al backend de FastAPI
//   (http://localhost:8000 por defecto). Así no hace falta configurar CORS.
// - src/config.js (usarDatosSimulados) decide si la interfaz usa datos simulados
//   o el backend real; VITE_USE_MOCKS en un .env tiene prioridad si existe.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [react()],
    base: env.VITE_BASE || '/',
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: env.VITE_API_URL || 'http://localhost:8000',
          changeOrigin: true,
        },
      },
    },
    build: {
      chunkSizeWarningLimit: 1200,
    },
  }
})
