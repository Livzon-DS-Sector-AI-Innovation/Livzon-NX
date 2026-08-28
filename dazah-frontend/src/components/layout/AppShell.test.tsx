import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

describe('application shell permission boundary', () => {
  it('keeps denied-module rendering and mapped-page gating in the shell', () => {
    const sourcePath = fileURLToPath(new URL('./AppShell.tsx', import.meta.url))
    const source = readFileSync(sourcePath, 'utf8')

    expect(source).toContain('暂无模块访问权限')
    expect(source).toContain('MappedMenuPageGate')
    expect(source).toContain('getAuthorizedModuleMenus')
  })
})
