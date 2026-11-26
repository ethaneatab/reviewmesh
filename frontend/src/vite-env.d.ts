/// <reference types="vite/client" />
declare const __REPO_URL__: string
declare const __GIT_SHA__: string
declare module '*.md?raw' {
  const text: string
  export default text
}
