import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('system permission page contract', () => {
  it('keeps all five permission administration entry points in the app tree', () => {
    const pages = [
      'roles',
      'user-roles',
      'menus',
      'dept-roles',
      'permission-verification',
    ]

    for (const page of pages) {
      const source = readFileSync(
        resolve(process.cwd(), `src/app/(dashboard)/system/${page}/page.tsx`),
        'utf8',
      )
      expect(source).toContain('export default')
    }
  })
})
