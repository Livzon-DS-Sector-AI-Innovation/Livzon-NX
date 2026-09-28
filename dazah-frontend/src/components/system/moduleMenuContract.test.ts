import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('system permission page contract', () => {
  it('keeps the four supported permission administration routes', () => {
    const pages = [
      'roles',
      'user-roles',
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

  it('retires the legacy menu editor while keeping system permissions in settings', () => {
    expect(existsSync(resolve(process.cwd(), 'src/app/(dashboard)/system/menus/page.tsx'))).toBe(false)
    expect(existsSync(resolve(process.cwd(), 'src/components/system/MenuManager.tsx'))).toBe(false)
    const settings = readFileSync(resolve(process.cwd(), 'src/components/settings/SettingsAdminClient.tsx'), 'utf8')
    expect(settings).toContain('SystemPermissionsPanel')
    expect(settings).not.toContain('MenuManager')
  })
})
