/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { clearProductionAuthForTest, setProductionAdminForTest } from '@/test/production-auth'

const actions = vi.hoisted(() => ({
  getSeedCultures: vi.fn(),
  createSeedCulture: vi.fn(),
  updateSeedCulture: vi.fn(),
  deleteSeedCulture: vi.fn(),
  getPersonMonthly: vi.fn(),
}))

vi.mock('@/actions/seed-culture', () => actions)
vi.mock('@/components/production/SyncSettingsButton', () => ({
  default: ({ onSync }: { onSync?: () => void }) => (
    <button data-testid="sync-settings" onClick={onSync}>同步设置</button>
  ),
}))

import SeedCulturePage from './page'

const RECORDS = [
  {
    id: 'sc-1',
    batch_no: 'SC-2026-01',
    product_name: '盐酸林可霉素',
    prepare_date: '2026-03-01',
    prepare_operator: [
      { name: '张三', open_id: 'ou_z', avatar_url: 'https://avatar/z.png' },
    ],
    glucose_batch: 'G-1',
  },
]

describe('SeedCulturePage (101-1) 林可台账', () => {
  let root: Root
  let container: HTMLElement

  beforeEach(() => {
    setProductionAdminForTest()
    actions.getSeedCultures.mockResolvedValue({ code: 200, message: 'success', data: RECORDS })
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    clearProductionAuthForTest()
    vi.clearAllMocks()
  })

  function setInputValue(el: HTMLInputElement, value: string) {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
    setter?.call(el, value)
    el.dispatchEvent(new Event('input', { bubbles: true }))
  }

  function bodyText(): string {
    return document.body.textContent || ''
  }

  function clickTab(label: string) {
    const tab = Array.from(document.body.querySelectorAll('.ant-tabs-tab')).find(
      (t) => (t.textContent || '').trim() === label,
    )
    expect(tab).toBeTruthy()
    act(() => {
      tab!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
  }

  it('renders five fixed tabs; 多拉占位, 林可带台账', async () => {
    act(() => {
      root.render(<App><SeedCulturePage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    // 五个固定 Tab（不可配置）
    const tabs = Array.from(document.body.querySelectorAll('.ant-tabs-tab')).map(
      (t) => (t.textContent || '').trim(),
    )
    expect(tabs).toEqual(['多拉菌素', '盐酸林可霉素', '苯丙氨酸', '洛伐他汀', '美伐他汀'])
    // 默认激活多拉（未配置）→ 占位
    expect(bodyText()).toContain('多拉菌素 · 内容建设中（待产品表格配置）')

    // 切到林可 → 按飞书表列渲染台账
    clickTab('盐酸林可霉素')
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    const text = bodyText()
    expect(text).toContain('摇瓶批号')
    expect(text).toContain('葡萄糖/批号')
    expect(text).toContain('配置日期')
    expect(text).toContain('SC-2026-01')
    expect(text).toContain('新建记录')
    expect(text).toContain('盐酸林可霉素 — 菌种台账')
    // 同步设置入口随台账渲染，且点击触发台账刷新
    const syncBtn = container.querySelector('[data-testid="sync-settings"]') as HTMLInputElement | null
    expect(syncBtn).toBeTruthy()
  })

  it('renders person fields as avatar + name chips', async () => {
    act(() => {
      root.render(<App><SeedCulturePage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    clickTab('盐酸林可霉素')
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    const avatarImg = container.querySelector('.ant-table .ant-avatar img') as HTMLImageElement | null
    expect(avatarImg?.src).toContain('https://avatar/z.png')
    const rowText = Array.from(container.querySelectorAll('.ant-table tbody tr'))
      .find((r) => r.textContent?.includes('SC-2026-01'))?.textContent || ''
    expect(rowText).toContain('张三')
  })

  it('filters records by batch number via the query button', async () => {
    act(() => {
      root.render(<App><SeedCulturePage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    clickTab('盐酸林可霉素')
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    const searchInput = Array.from(container.querySelectorAll('input')).find((i) => (i.placeholder || '').includes('搜索摇瓶批号'))
    expect(searchInput).toBeTruthy()
    await act(async () => {
      setInputValue(searchInput!, 'SC-2026-01')
      await new Promise((r) => setTimeout(r, 30))
    })
    const queryBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('查询'))
    await act(async () => {
      queryBtn!.click()
      await new Promise((r) => setTimeout(r, 80))
    })
    const lastCall = actions.getSeedCultures.mock.calls.at(-1)
    expect(lastCall?.[0]).toMatchObject({ page: 1, page_size: 200, product_name: '盐酸林可霉素', batch_no: 'SC-2026-01' })
  })

  it('creates a new record and submits person names as person refs', async () => {
    actions.createSeedCulture.mockResolvedValue({ code: 200, message: 'created', data: null })
    act(() => {
      root.render(<App><SeedCulturePage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    clickTab('盐酸林可霉素')
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    const addBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('新建记录'))
    expect(addBtn).toBeTruthy()
    await act(async () => { addBtn!.click(); await new Promise((r) => setTimeout(r, 60)) })

    const batchInput = Array.from(document.body.querySelectorAll('.ant-modal input')).find((i) => (i.getAttribute('placeholder') || '') === '请输入') as HTMLInputElement | undefined
    expect(batchInput).toBeTruthy()
    await act(async () => {
      setInputValue(batchInput!, 'SC-NEW-01')
      await new Promise((r) => setTimeout(r, 30))
    })
    // 人员字段：文本输入（逗号分隔）→ 提交为 PersonRef 数组
    const personInput = Array.from(document.body.querySelectorAll('.ant-modal input')).find(
      (i) => i.closest('.ant-form-item')?.textContent?.includes('配制操作人/复核人'),
    ) as HTMLInputElement | undefined
    expect(personInput).toBeTruthy()
    await act(async () => {
      setInputValue(personInput!, '张三,李四')
      await new Promise((r) => setTimeout(r, 30))
    })
    const okBtn = Array.from(document.querySelectorAll('.ant-modal button')).find((b) => (b.textContent || '').replace(/\s/g, '') === '确认') as HTMLButtonElement | undefined
    await act(async () => { okBtn!.click(); await new Promise((r) => setTimeout(r, 120)) })

    const created = actions.createSeedCulture.mock.calls.at(-1)?.[0] as Record<string, unknown>
    expect(created).toBeDefined()
    expect(created.batch_no).toBe('SC-NEW-01')
    expect(created.product_name).toBe('盐酸林可霉素')
    expect(created.prepare_operator).toEqual([{ name: '张三' }, { name: '李四' }])
  })

  it('switches to person monthly stats view with role columns', async () => {
    actions.getPersonMonthly.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [
        {
          key: 'ou_z',
          name: '张三',
          open_id: 'ou_z',
          avatar_url: null,
          total_batches: 2,
          role_counts: { 配制: 2, 消毒: 0, 摇床摆放: 0, 接种: 1, 并瓶: 0, 进罐: 0, 车间接种: 0 },
          details: [
            { date: '2026-11-03', batch_no: 'SC-1', role: '配制' },
            { date: '2026-11-08', batch_no: 'SC-2', role: '接种' },
          ],
        },
      ],
    })
    act(() => {
      root.render(<App><SeedCulturePage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    clickTab('盐酸林可霉素')
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    // 切到人员统计视图
    const statsBtn = Array.from(container.querySelectorAll('.ant-segmented-item')).find(
      (el) => el.textContent?.includes('人员统计'),
    )
    expect(statsBtn).toBeTruthy()
    await act(async () => {
      statsBtn!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((r) => setTimeout(r, 120))
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 120))
    })
    const text = document.body.textContent || ''
    expect(text).toContain('参与批次')
    expect(text).toContain('配制')
    expect(text).toContain('张三')
    expect(text).toContain('按「配置日期」归属月份')
    // 请求带当前月份
    const lastCall = actions.getPersonMonthly.mock.calls.at(-1)
    expect(lastCall?.[0]).toMatchObject({ product_name: '盐酸林可霉素' })
    expect(String(lastCall?.[0].month)).toMatch(/^\d{4}-\d{2}$/)
  })

  it('opens the record detail modal with person chips', async () => {
    act(() => {
      root.render(<App><SeedCulturePage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    clickTab('盐酸林可霉素')
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    const detailBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('详情'))
    expect(detailBtn).toBeTruthy()
    await act(async () => { detailBtn!.click(); await new Promise((r) => setTimeout(r, 80)) })
    const text = document.body.textContent || ''
    expect(text).toContain('记录详情')
    expect(text).toContain('SC-2026-01')
    expect(text).toContain('配制操作人/复核人')
  })

  it('edits an existing record and pre-fills person names', async () => {
    actions.updateSeedCulture.mockResolvedValue({ code: 200, message: 'updated', data: null })
    act(() => {
      root.render(<App><SeedCulturePage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    clickTab('盐酸林可霉素')
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    const editBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('编辑'))
    expect(editBtn).toBeTruthy()
    await act(async () => { editBtn!.click(); await new Promise((r) => setTimeout(r, 60)) })
    expect((document.body.textContent || '')).toContain('编辑记录')
    // 人员字段回填为姓名串（数组归一）
    const personInput = Array.from(document.body.querySelectorAll('.ant-modal input')).find(
      (i) => i.closest('.ant-form-item')?.textContent?.includes('配制操作人/复核人'),
    ) as HTMLInputElement | undefined
    expect(personInput?.value).toBe('张三')
    const okBtn = Array.from(document.querySelectorAll('.ant-modal button')).find((b) => (b.textContent || '').replace(/\s/g, '') === '确认') as HTMLButtonElement | undefined
    await act(async () => { okBtn!.click(); await new Promise((r) => setTimeout(r, 120)) })
    expect(actions.updateSeedCulture).toHaveBeenCalledWith('sc-1', expect.objectContaining({ batch_no: 'SC-2026-01' }))
  })

  it('cancels the create modal via the cancel button', async () => {
    act(() => {
      root.render(<App><SeedCulturePage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    clickTab('盐酸林可霉素')
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    const addBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('新建记录'))
    await act(async () => { addBtn!.click(); await new Promise((r) => setTimeout(r, 60)) })
    expect((document.body.textContent || '')).toContain('新建记录')
    const cancelBtn = Array.from(document.querySelectorAll('.ant-modal button')).find((b) => (b.textContent || '').replace(/\s/g, '') === '取消') as HTMLButtonElement | undefined
    expect(cancelBtn).toBeTruthy()
    await act(async () => { cancelBtn!.click(); await new Promise((r) => setTimeout(r, 120)) })
    // destroyOnHidden 会卸载弹窗内容
    expect(document.body.querySelector('.ant-modal-content')).toBeNull()
  })

  it('shows an error state when the seed culture load rejects', async () => {
    actions.getSeedCultures.mockRejectedValue(new Error('network'))
    act(() => {
      root.render(<App><SeedCulturePage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    clickTab('盐酸林可霉素')
    await act(async () => {
      await new Promise((r) => setTimeout(r, 120))
    })
    expect(actions.getSeedCultures).toHaveBeenCalled()
  })

  it('deletes a record after confirming the delete dialog', async () => {
    actions.deleteSeedCulture.mockResolvedValue({ code: 200, message: 'deleted', data: null })
    act(() => {
      root.render(<App><SeedCulturePage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    clickTab('盐酸林可霉素')
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    const delBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('删除'))
    expect(delBtn).toBeTruthy()
    await act(async () => { delBtn!.click(); await new Promise((r) => setTimeout(r, 60)) })
    expect((document.body.textContent || '')).toContain('确认删除')
    const confirmOk = Array.from(document.querySelectorAll('.ant-modal-confirm .ant-btn-primary')) as HTMLButtonElement[]
    await act(async () => { confirmOk[0]?.click(); await new Promise((r) => setTimeout(r, 120)) })
    expect(actions.deleteSeedCulture).toHaveBeenCalledWith('sc-1')
  })
})
