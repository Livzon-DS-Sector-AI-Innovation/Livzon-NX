import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

describe('HR chat retirement', () => {
  it('removes the HR-only store and public component export', () => {
    const root = process.cwd()
    expect(existsSync(resolve(root, 'src/stores/hrChat.ts'))).toBe(false)
    const hrExports = readFileSync(resolve(root, 'src/components/hr/index.ts'), 'utf8')
    expect(hrExports).not.toContain('HrChatbot')
  })
})
