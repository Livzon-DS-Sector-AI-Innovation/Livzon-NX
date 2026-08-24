import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

describe('Feishu data migrated component contract', () => {
  it('keeps the shared module data source component available', () => {
    const sourcePath = fileURLToPath(new URL('./ModuleFeishuDataSourcePage.tsx', import.meta.url))
    const source = readFileSync(sourcePath, 'utf8')

    expect(existsSync(sourcePath)).toBe(true)
    expect(source).toContain('export function ModuleFeishuDataSourcePage')
    expect(source).toContain('moduleCode')
  })
})
