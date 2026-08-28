import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

describe('product migrated component contract', () => {
  it('keeps the product ledger client and its server-action boundary', () => {
    const sourcePath = fileURLToPath(new URL('./ProductClient.tsx', import.meta.url))
    const source = readFileSync(sourcePath, 'utf8')

    expect(existsSync(sourcePath)).toBe(true)
    expect(source).toContain('export default function ProductClient')
    expect(source).toContain("@/actions/product")
    expect(source).toContain("@/lib/api/product")
  })
})
