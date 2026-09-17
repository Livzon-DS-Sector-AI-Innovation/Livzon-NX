import { existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { getPageKeyByPath, moduleMenus } from '@/lib/menu-config'

describe('retired CPV surface', () => {
  it('has no navigable page or remaining client API entry', () => {
    const qualityMenu = moduleMenus.find((menu) => menu.key === 'quality')
    expect(JSON.stringify(qualityMenu)).not.toContain('/quality/cpv')
    expect(getPageKeyByPath('/quality/cpv')).toBeUndefined()
    expect(getPageKeyByPath('/quality/cpv/product-1/cpp')).toBeUndefined()
    expect(existsSync(resolve(process.cwd(), 'src/lib/api/quality-cpv.ts'))).toBe(false)
    expect(existsSync(resolve(process.cwd(), 'src/app/(dashboard)/quality/cpv/page.tsx'))).toBe(false)
  })
})
