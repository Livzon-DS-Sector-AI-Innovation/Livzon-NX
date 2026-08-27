import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

describe('production label verification component contract', () => {
  it('keeps the migrated client component available for the production route', () => {
    const sourcePath = fileURLToPath(new URL('./LabelVerificationClient.tsx', import.meta.url))
    const source = readFileSync(sourcePath, 'utf8')

    expect(existsSync(sourcePath)).toBe(true)
    expect(source).toContain('export default function LabelVerificationClient')
    expect(source).toContain('autoCompareVideo')
  })
})
