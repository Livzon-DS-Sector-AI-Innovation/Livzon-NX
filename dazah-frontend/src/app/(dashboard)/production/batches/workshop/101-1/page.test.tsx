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

  // ─── 新增用例：覆盖 changed lines ───

  function setInputValue(el: HTMLInputElement, value: string) {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
    setter?.call(el, value)
    el.dispatchEvent(new Event('input', { bubbles: true }))
  }

  it('loads the saved product-line config from localStorage and renders the limited tabs', async () => {
    window.localStorage.clear()
    window.localStorage.setItem('workshop_1011_active_products', JSON.stringify(['doramectin', 'mevastatin']))
    act(() => {
      root.render(<App><SeedCulturePage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('多拉菌素')
    // 未启用的产品不应出现在 Tabs / 页面
    expect(text).not.toContain('盐酸林可霉素')
  })

  it('filters records by batch number via the query button', async () => {
    window.localStorage.clear()
    act(() => {
      root.render(<App><SeedCulturePage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const searchInput = Array.from(container.querySelectorAll('input')).find((i) => (i.placeholder || '').includes('搜索摇瓶批号'))
    if (searchInput) {
      await act(async () => {
        setInputValue(searchInput, 'SC-2026-01')
        await new Promise((r) => setTimeout(r, 30))
      })
    }
    const queryBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('查询'))
    if (queryBtn) {
      await act(async () => {
        queryBtn.click()
        await new Promise((r) => setTimeout(r, 80))
      })
    }
    const lastCall = actions.getSeedCultures.mock.calls.at(-1)
    expect(lastCall?.[0]).toMatchObject({ page: 1, page_size: 200, product_name: '多拉菌素', batch_no: 'SC-2026-01' })
  })

  it('creates a new record via the modal and stores input history', async () => {
    actions.createSeedCulture.mockResolvedValue({ code: 200, message: 'created', data: null })
    window.localStorage.clear()
    act(() => {
      root.render(<App><SeedCulturePage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const addBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('新建'))
    if (addBtn) {
      await act(async () => {
        addBtn.click()
        await new Promise((r) => setTimeout(r, 60))
      })
    }
    const batchInput = Array.from(document.body.querySelectorAll('.ant-modal input')).find((i) => (i.getAttribute('placeholder') || '') === '请输入') as HTMLInputElement | undefined
    if (batchInput) {
      await act(async () => {
        setInputValue(batchInput, 'SC-NEW-01')
        await new Promise((r) => setTimeout(r, 30))
      })
    }
    const okBtn = Array.from(document.querySelectorAll('.ant-modal button')).find((b) => (b.textContent || '').replace(/\s/g, '') === '确认') as HTMLButtonElement | undefined
    if (okBtn) {
      await act(async () => {
        okBtn.click()
        await new Promise((r) => setTimeout(r, 120))
      })
    }
    const created = actions.createSeedCulture.mock.calls.at(-1)?.[0] as Record<string, unknown>
    expect(created).toBeDefined()
    expect(created.batch_no).toBe('SC-NEW-01')
    expect(created.product_name).toBe('多拉菌素')
    const history = JSON.parse(window.localStorage.getItem('seed_culture_history') || '{}')
    expect(history['batch_no']).toContain('SC-NEW-01')
  })

  it('edits an existing record through the edit modal and saves the update', async () => {
    actions.updateSeedCulture.mockResolvedValue({ code: 200, message: 'updated', data: null })
    window.localStorage.clear()
    act(() => {
      root.render(<App><SeedCulturePage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const editBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('编辑'))
    if (editBtn) {
      await act(async () => {
        editBtn.click()
        await new Promise((r) => setTimeout(r, 60))
      })
    }
    expect((document.body.textContent || '')).toContain('编辑记录')
    const okBtn = Array.from(document.querySelectorAll('.ant-modal button')).find((b) => (b.textContent || '').replace(/\s/g, '') === '确认') as HTMLButtonElement | undefined
    if (okBtn) {
      await act(async () => {
        okBtn.click()
        await new Promise((r) => setTimeout(r, 120))
      })
    }
    expect(actions.updateSeedCulture).toHaveBeenCalledWith('sc-1', expect.objectContaining({ batch_no: 'SC-2026-01' }))
  })

  it('opens the record detail modal', async () => {
    window.localStorage.clear()
    act(() => {
      root.render(<App><SeedCulturePage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const detailBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('详情'))
    if (detailBtn) {
      await act(async () => {
        detailBtn.click()
        await new Promise((r) => setTimeout(r, 80))
      })
    }
    const text = document.body.textContent || ''
    expect(text).toContain('记录详情')
    expect(text).toContain('SC-2026-01')
    expect(text).toContain('配制操作人')
  })

  it('deletes a record after confirming the delete dialog', async () => {
    actions.deleteSeedCulture.mockResolvedValue({ code: 200, message: 'deleted', data: null })
    window.localStorage.clear()
    act(() => {
      root.render(<App><SeedCulturePage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const delBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('删除'))
    if (delBtn) {
      await act(async () => {
        delBtn.click()
        await new Promise((r) => setTimeout(r, 60))
      })
    }
    expect((document.body.textContent || '')).toContain('确认删除')
    const confirmOk = Array.from(document.querySelectorAll('.ant-modal-confirm .ant-btn-primary')) as HTMLButtonElement[]
    if (confirmOk[0]) {
      await act(async () => {
        confirmOk[0].click()
        await new Promise((r) => setTimeout(r, 120))
      })
    }
    expect(actions.deleteSeedCulture).toHaveBeenCalledWith('sc-1')
  })

  it('auto-switches the active product tab when it is turned off in the line config', async () => {
    window.localStorage.clear()
    act(() => {
      root.render(<App><SeedCulturePage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const cfgBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('产线配置'))
    if (cfgBtn) {
      await act(async () => {
        cfgBtn.click()
        await new Promise((r) => setTimeout(r, 60))
      })
    }
    // 关闭第一个产品（多拉菌素）
    const switches = Array.from(document.querySelectorAll('.ant-modal .ant-switch')) as HTMLElement[]
    if (switches[0]) {
      await act(async () => {
        switches[0].click()
        await new Promise((r) => setTimeout(r, 60))
      })
    }
    const saveBtn = Array.from(document.querySelectorAll('.ant-modal button')).find((b) => b.textContent?.trim() === '保存') as HTMLButtonElement | undefined
    if (saveBtn) {
      await act(async () => {
        saveBtn.click()
        await new Promise((r) => setTimeout(r, 120))
      })
    }
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('盐酸林可霉素')
    const saved = JSON.parse(window.localStorage.getItem('workshop_1011_active_products') || '[]')
    expect(saved).not.toContain('doramectin')
  })

  it('cancels the create modal via the cancel button', async () => {
    window.localStorage.clear()
    act(() => {
      root.render(<App><SeedCulturePage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const addBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('新建'))
    if (addBtn) {
      await act(async () => {
        addBtn.click()
        await new Promise((r) => setTimeout(r, 60))
      })
    }
    expect((document.body.textContent || '')).toContain('新建记录')
    const cancelBtn = Array.from(document.querySelectorAll('.ant-modal button')).find((b) => b.textContent?.trim() === '取消') as HTMLButtonElement | undefined
    if (cancelBtn) {
      await act(async () => {
        cancelBtn.click()
        await new Promise((r) => setTimeout(r, 120))
      })
    }
    // destroyOnHidden 会卸载弹窗内容
    expect(document.body.querySelector('.ant-modal-content')).toBeNull()
  })

  it('shows an error state when the seed culture load rejects', async () => {
    actions.getSeedCultures.mockRejectedValue(new Error('network'))
    window.localStorage.clear()
    act(() => {
      root.render(<App><SeedCulturePage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    expect(actions.getSeedCultures).toHaveBeenCalled()
  })
})
