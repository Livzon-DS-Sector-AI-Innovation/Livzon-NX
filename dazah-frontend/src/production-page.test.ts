import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

describe('production migrated page contract', () => {
  it('keeps the production dashboard page physically resolvable', () => {
    const pagePath = fileURLToPath(
      new URL('./app/(dashboard)/production/page.tsx', import.meta.url),
    )
    const source = readFileSync(pagePath, 'utf8')

    expect(existsSync(pagePath)).toBe(true)
    expect(source).toMatch(/export default function/)
  })
})
