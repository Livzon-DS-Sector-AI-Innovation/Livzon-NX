import { describe, expect, it } from 'vitest'
import { moduleMenus } from '@/lib/menu-config'

describe('quality migrated menu contract', () => {
  it('exposes the document, inspection, OOS/OOT and validation areas', () => {
    const quality = moduleMenus.find((menu) => menu.moduleCode === 'quality')
    const paths = JSON.stringify(quality?.children ?? [])

    expect(paths).toContain('/quality/documents')
    expect(paths).toContain('/quality/inspection')
    expect(paths).toContain('/quality/oos-oot')
    expect(paths).toContain('/quality/validation')
  })
})
