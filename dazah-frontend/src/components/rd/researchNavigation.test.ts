import { describe, expect, it } from 'vitest'
import { getPageKeyByPath, moduleMenus } from '@/lib/menu-config'

describe('research navigation after optimization retirement', () => {
  it('keeps research tools without advertising the retired route', () => {
    const research = moduleMenus.find((menu) => menu.key === 'rd')
    const paths = research?.children.map((menu) => menu.path)

    expect(paths).not.toContain('/rd/bayesian')
    expect(paths).toEqual(expect.arrayContaining([
      '/rd/projects', '/rd/ich-analysis', '/rd/pilot-workflow',
    ]))
    expect(getPageKeyByPath('/rd/bayesian')).toBeUndefined()
  })
})
