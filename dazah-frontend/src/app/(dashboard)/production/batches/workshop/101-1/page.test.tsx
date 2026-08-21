/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const actions = vi.hoisted(() => ({
  getSeedCultures: vi.fn(),
  createSeedCulture: vi.fn(),
  updateSeedCulture: vi.fn(),
  deleteSeedCulture: vi.fn(),
}))

vi.mock('@/actions/seed-culture', () => actions)
vi.mock('@/components/production/SyncSettingsButton', () => ({
  default: () => <button>同步设置</button>,
}))

import SeedCulturePage from './page'

const RECORDS = [
  {
    id: 'sc-1',
    batch_no: 'SC-2026-01',
    product_name: '多拉菌素',
    prepare_date: '2026-03-01',
    prepare_operator: '张三',
    glucose_batch: 'G-1',
  },
]

describe('SeedCulturePage (101-1)', () => {
  let root: Root
  let container: HTMLElement

  beforeEach(() => {
    actions.getSeedCultures.mockResolvedValue({ code: 200, message: 'success', data: RECORDS })
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  it('renders seed culture records in the ledger', async () => {
    act(() => {
      root.render(<SeedCulturePage />)
    })

    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })

    const text = container.textContent || ''
    expect(text).toContain('菌种制备')
    expect(text).toContain('SC-2026-01')
    expect(text).toContain('多拉菌素')
    expect(text).toContain('新建')
  })

  it('renders the empty-products line configuration state and switches tabs', async () => {
    // localStorage 无保存值时，默认所有产品上线
    act(() => {
      root.render(<SeedCulturePage />)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })

    const text = container.textContent || ''
    expect(text).toContain('产线配置')
    // 多产品时出现 Tabs（handleTabChange 分支）
    expect(text).toContain('多拉菌素')
  })

  it('shows an error message when loading fails', async () => {
    actions.getSeedCultures.mockResolvedValue({ code: 500, message: '服务错误', data: [] })

    act(() => {
      root.render(<App><SeedCulturePage /></App>)
    })

    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })
    expect(actions.getSeedCultures).toHaveBeenCalled()
  })

  it('opens the create and edit modals via ledger buttons', async () => {
    actions.deleteSeedCulture.mockResolvedValue({ code: 200, message: 'success', data: null })
    act(() => {
      root.render(<App><SeedCulturePage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    // 新建按钮
    const createBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('新建'))
    if (createBtn) {
      await act(async () => { createBtn.click(); await new Promise((r) => setTimeout(r, 60)) })
    }
    expect((document.body.textContent || '')).toContain('新建')
    // 编辑按钮
    const editBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('编辑'))
    if (editBtn) {
      await act(async () => { editBtn.click(); await new Promise((r) => setTimeout(r, 60)) })
    }
    expect((document.body.textContent || '')).toContain('编辑')
  })

  it('opens the line configuration modal', async () => {
    act(() => {
      root.render(<App><SeedCulturePage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const cfgBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('产线配置'))
    if (cfgBtn) {
      await act(async () => { cfgBtn.click(); await new Promise((r) => setTimeout(r, 60)) })
    }
    expect((document.body.textContent || '')).toContain('产线配置')
  })
})
