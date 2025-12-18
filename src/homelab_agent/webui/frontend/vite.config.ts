import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    // Output to dist folder which will be included in the package
    outDir: '../static',
    emptyOutDir: true,
  },
})
