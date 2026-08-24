import { describe, expect, it } from 'vitest'
import { moduleMenus } from '@/lib/menu-config'

describe('registration migrated menu contract', () => {
  it('exposes projects, certificates, fees and knowledge base', () => {
    const registration = moduleMenus.find((menu) => menu.moduleCode === 'registration')
    const paths = JSON.stringify(registration?.children ?? [])

    expect(paths).toContain('/registration/project')
    expect(paths).toContain('/registration/certificate-management')
    expect(paths).toContain('/registration/fees')
    expect(paths).toContain('/registration/knowledge')
  })
})
