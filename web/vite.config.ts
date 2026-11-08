import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// VITE_BASE lets the same build run at the domain root (Vercel, local dev)
// or under a sub-path such as GitHub Pages (/PruebaNASA/).
export default defineConfig({
  base: process.env.VITE_BASE ?? '/',
  plugins: [react()],
})
