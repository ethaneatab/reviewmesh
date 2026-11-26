import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { execSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

// The GitHub account lives in exactly one place: project.json at the repo root.
const project = JSON.parse(readFileSync(fileURLToPath(new URL('../project.json', import.meta.url)), 'utf8'))
const repoUrl = process.env.VITE_REPO_URL || project.repo_url
let sha = process.env.VITE_GIT_SHA || ''
if (!sha) {
  try { sha = execSync('git rev-parse HEAD').toString().trim() } catch { sha = 'HEAD' }
}

export default defineConfig({
  plugins: [react()],
  define: {
    __REPO_URL__: JSON.stringify(repoUrl),
    __GIT_SHA__: JSON.stringify(sha),
  },
  server: {
    port: 5189,
    strictPort: true,
    // docs/interview.md and docs/problems.md are imported as text from outside the frontend folder.
    fs: { allow: ['..'] },
    proxy: {
      '/api/intake': { target: 'http://127.0.0.1:8890', rewrite: (p) => p.replace(/^\/api\/intake/, '') },
      '/api/review': { target: 'http://127.0.0.1:8891', rewrite: (p) => p.replace(/^\/api\/review/, '') },
      '/learn/api': { target: 'http://127.0.0.1:8890' },
      // Teaching videos are files in docs/videos, served by the intake API.
      '/videos': { target: 'http://127.0.0.1:8890' },
    },
  },
  preview: {
    port: 5189,
    proxy: {
      '/api/intake': { target: 'http://127.0.0.1:8890', rewrite: (p) => p.replace(/^\/api\/intake/, '') },
      '/api/review': { target: 'http://127.0.0.1:8891', rewrite: (p) => p.replace(/^\/api\/review/, '') },
      '/learn/api': { target: 'http://127.0.0.1:8890' },
      '/videos': { target: 'http://127.0.0.1:8890' },
    },
  },
})
