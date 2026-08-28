/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/components/production/FASheetsSyncButton', () => ({
  default: () => <button>同步</button>,
}))
vi.mock('@/components/production/FATraceButton', () => ({
  default: () => <button>追溯</button>,
}))

import AcidificationPage from './page'

const ITEMS = [
  {
    日期: '2026-03-01',
    批号: 'FA-2603-1',
    酸罐: 'T1',
    进料量: 10,
    滤液量: 8,
    滤液含量: 90,
    产品量: 7.2,
    收率: 90.5,
  },
  {
    日期: '2026-03-01',
    批号: 'FA-2603-1',
    酸罐: 'T2',
    进料量: 12,
    滤液量: 9,
    滤液含量: 88,
    产品量: 7.9,
    收率: 88.2,
  },
]

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

function fetchMock(url: string) {
  if (url.includes('/acidification/flat-list')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: { items: ITEMS, total: 2 } }))
  }
  if (url.includes('/monthly-averages')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: { data: [], columns: [] } }))
  }
  return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
}

describe('AcidificationPage (203)', () => {
  let root: Root
  let container: HTMLElement

  beforeEach(() => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
  })

  it('renders the acidification ledger with merged batch rows', async () => {
    vi.stubGlobal('fetch', vi.fn(fetchMock))

    act(() => {
      root.render(<AcidificationPage />)
    })

    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })

    const text = container.textContent || ''
    expect(text).toContain('酸化过滤')
    expect(text).toContain('FA-2603-1')
    expect(text).toContain('共 2 行')
    expect(text).toContain('返回车间')
  })
})
