import { cpSync, existsSync } from 'node:fs'

const standaloneRoot = '.next/standalone'

if (!existsSync(`${standaloneRoot}/server.js`)) {
  throw new Error('Standalone production bundle is missing. Run `pnpm build` first.')
}

cpSync('.next/static', `${standaloneRoot}/.next/static`, { recursive: true })
if (existsSync('public')) {
  cpSync('public', `${standaloneRoot}/public`, { recursive: true })
}

await import('../.next/standalone/server.js')
