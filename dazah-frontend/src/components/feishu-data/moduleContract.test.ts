import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it, vi } from 'vitest'

vi.mock('./OverviewComponents', () => {
  throw new Error('The shared Feishu entry must not load the chart components')
})

describe('Feishu data migrated component contract', () => {
  it('exposes the page gate without loading the chart components', async () => {
    const { MappedMenuPageGate } = await import('./index')

    expect(MappedMenuPageGate).toBeTypeOf('function')
  })

  it('keeps the shared module data source component available', () => {
    const sourcePath = fileURLToPath(new URL('./ModuleFeishuDataSourcePage.tsx', import.meta.url))
    const source = readFileSync(sourcePath, 'utf8')

    expect(existsSync(sourcePath)).toBe(true)
    expect(source).toContain('export function ModuleFeishuDataSourcePage')
    expect(source).toContain('moduleCode')
  })
})
