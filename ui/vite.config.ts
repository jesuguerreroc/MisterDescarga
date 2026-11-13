import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// base relativa: pywebview carga los archivos desde el propio .exe
export default defineConfig({
  base: './',
  plugins: [react(), tailwindcss()],
})
