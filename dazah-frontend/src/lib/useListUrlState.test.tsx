/* @vitest-environment happy-dom */
import { act, createElement } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'

const navigation = vi.hoisted(() => ({ pathname: '/purchasing/supplier', query: 'page=4&keyword=旧&tab=active', replace: vi.fn() }))
vi.mock('next/navigation', () => ({
  usePathname: () => navigation.pathname,
  useSearchParams: () => new URLSearchParams(navigation.query),
  useRouter: () => ({ replace: navigation.replace }),
}))

import { useListUrlState } from './useListUrlState'

function Harness() {
  const { page, setListQuery, detailHref } = useListUrlState()
  return createElement('div', null,
    createElement('span', null, `第${page}页`),
    createElement('button', { onClick: () => setListQuery({ keyword: '新' }, true) }, '查询'),
    createElement('a', { href: detailHref('/purchasing/supplier/7') }, '详情'),
  )
}

afterEach(() => { document.body.replaceChildren(); vi.clearAllMocks() })

describe('useListUrlState', () => {
  it('resets pagination on search and carries the list URL into detail', async () => {
    vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
    const host = document.createElement('div')
    document.body.append(host)
    const root = createRoot(host)
    try {
      await act(async () => root.render(createElement(Harness)))
      expect(host.textContent).toContain('第4页')
      expect(host.querySelector('a')?.getAttribute('href')).toContain('returnTo=%2Fpurchasing%2Fsupplier')
      await act(async () => host.querySelector('button')?.click())
      expect(navigation.replace).toHaveBeenCalledWith('/purchasing/supplier?keyword=%E6%96%B0&tab=active', { scroll: false })
    } finally {
      await act(async () => root.unmount())
      vi.unstubAllGlobals()
    }
  })
})
