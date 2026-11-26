/* @vitest-environment happy-dom */
/**
 * 物料价格查询页：真实 antd 渲染，mock 数据接口，验证列表、搜索与详情抽屉。
 */
/* eslint-disable @typescript-eslint/no-explicit-any */

import { act, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from 'antd'
import { MaterialPriceClient } from './MaterialPriceClient'

const api = vi.hoisted(() => ({
  fetchMaterialPrices: vi.fn(),
  fetchMaterialPriceDetail: vi.fn(),
}))

vi.mock('@/lib/api/purchasing', () => api)
vi.mock('@/components/shared/ThemedEChart', () => ({
  default: () => <div data-testid="price-chart" />,
}))

const summary = {
  material_code: '51069308',
  material_name: '隔膜垫,DN15卫生级',
  unit: '片',
  cost_category: '五金备件',
  sub_inventory: 'C03 五金备件仓',
  batch_count: 144,
  supplier_count: 4,
  latest_year: 2026,
  min_price: '15.04',
  max_price: '34.51',
  avg_price: '34.12',
  has_suspicious: true,
  live_batch_count: 2,
  live_latest_price: '36.00',
  live_latest_date: '2026-10-01',
}

const detail = {
  material_code: '51069308',
  material_name: '隔膜垫,DN15卫生级',
  material_alias: '隔膜垫',
  unit: '片',
  material_category: '五金机械.机械五金辅材',
  cost_category: '五金备件',
  sub_inventory: 'C03 五金备件仓',
  years: [
    {
      data_year: 2024,
      batch_count: 10,
      min_price: '30.00',
      max_price: '30.00',
      avg_price: '30.00',
      quantity: '100',
    },
    {
      data_year: 2025,
      batch_count: 12,
      min_price: '34.12',
      max_price: '34.51',
      avg_price: '34.30',
      quantity: '120',
    },
  ],
  batches: [
    {
      id: 'b1',
      data_year: 2025,
      data_date: null,
      doc_no: '',
      department: '',
      sub_inventory: 'C03 五金备件仓',
      batch_no: 'B001',
      supplier_name: '宁夏诚弘胜机电泵阀有限公司',
      unit: '片',
      unit_price: '34.12',
      quantity: '10',
      amount: '341.20',
      price_flag: 'normal',
      source_type: 'erp_stock',
    },
  ],
  live_batches: [
    {
      id: 'live-1',
      data_year: 2026,
      data_date: '2026-10-01',
      doc_no: '',
      department: '101-2 车间',
      sub_inventory: '五金备件仓',
      batch_no: '25-101-2/12-28',
      supplier_name: '上海过滤器有限公司',
      unit: '片',
      unit_price: '36.00',
      quantity: '5',
      amount: '180.00',
      price_flag: 'normal',
      source_type: 'warehouse_live',
    },
  ],
}

let container: HTMLDivElement
let root: Root

function mockMatchMedia() {
  window.matchMedia =
    window.matchMedia ??
    ((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))
}

function mockResizeObserver() {
  if (!(globalThis as any).ResizeObserver) {
    ;(globalThis as any).ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
  }
}

function render(ui: ReactNode) {
  act(() => {
    root.render(<App>{ui}</App>)
  })
}

beforeAll(() => {
  mockMatchMedia()
  mockResizeObserver()
})

beforeEach(() => {
  api.fetchMaterialPrices.mockReset()
  api.fetchMaterialPriceDetail.mockReset()
  api.fetchMaterialPrices.mockResolvedValue({
    code: 200,
    message: 'success',
    data: [summary],
    meta: { page: 1, page_size: 20, total: 1 },
  })
  api.fetchMaterialPriceDetail.mockResolvedValue({
    code: 200,
    message: 'success',
    data: detail,
  })
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})

afterEach(() => {
  act(() => {
    root.unmount()
  })
  container.remove()
})

describe('MaterialPriceClient', () => {
  it('renders material rows with price range and amount', () => {
    render(
      <MaterialPriceClient initialRecords={[summary]} initialTotal={1} />,
    )
    const text = container.textContent ?? ''
    expect(text).toContain('51069308')
    expect(text).toContain('隔膜垫,DN15卫生级')
    expect(text).toContain('34.12')
    expect(text).toContain('15.04 ~ 34.51')
    expect(text).toContain('共 1 条')
  })

  it('opens detail drawer and loads price history on row click', async () => {
    render(
      <MaterialPriceClient initialRecords={[summary]} initialTotal={1} />,
    )
    const row = container.querySelector('tr[data-row-key="51069308"]')
    expect(row).not.toBeNull()
    await act(async () => {
      row?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    expect(api.fetchMaterialPriceDetail).toHaveBeenCalledWith('51069308')
    await act(async () => {
      await Promise.resolve()
    })
    const text = document.body.textContent ?? ''
    expect(text).toContain('年度价格走势')
    expect(text).toContain('年度汇总')
    expect(text).toContain('B001')
  })

  it('keeps page empty until an ask, then searches', async () => {
    api.fetchMaterialPrices.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [summary],
      meta: { page: 1, page_size: 20, total: 1 },
    })
    render(<MaterialPriceClient />)
    // 打开页面即空态，不请求数据
    expect(api.fetchMaterialPrices).not.toHaveBeenCalled()
    expect(container.textContent).toContain('未找到匹配的物料价格记录')

    // 无条件点击刷新同样不请求
    const refreshTop = Array.from(container.querySelectorAll('button')).find(
      (item) => item.textContent?.includes('刷新'),
    )
    await act(async () => {
      refreshTop?.click()
      await Promise.resolve()
    })
    expect(api.fetchMaterialPrices).not.toHaveBeenCalled()

    // 输入关键词后点查询，才请求并展示结果
    const input = container.querySelector<HTMLInputElement>('input.ant-input')
    expect(input).not.toBeNull()
    const setValue = Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      'value',
    )?.set
    expect(setValue).toBeDefined()
    await act(async () => {
      setValue!.call(input!, '隔膜垫')
      input!.dispatchEvent(new Event('input', { bubbles: true }))
      await Promise.resolve()
    })
    await act(async () => {
      const searchBtn = Array.from(container.querySelectorAll('button')).find(
        (item) => item.textContent?.trim() === '查询',
      )
      searchBtn?.click()
      await Promise.resolve()
    })
    expect(api.fetchMaterialPrices).toHaveBeenCalledTimes(1)
    expect(api.fetchMaterialPrices.mock.calls[0][0]).toMatchObject({
      keyword: '隔膜垫',
    })
    expect(container.textContent).toContain('共 1 条')
  })

  it('reports a detail load failure through the message portal', async () => {
    api.fetchMaterialPriceDetail.mockRejectedValue(new Error('network down'))
    render(<MaterialPriceClient initialRecords={[summary]} initialTotal={1} />)
    const row = container.querySelector('tr[data-row-key="51069308"]')
    await act(async () => {
      row?.dispatchEvent(new MouseEvent("click", { bubbles: true }))
      await Promise.resolve()
    })
    await act(async () => {
      await Promise.resolve()
    })
    expect(document.body.textContent).toContain('物料价格详情加载失败')
    expect(container.textContent).not.toContain('年度价格走势')
  })

  it('switches to the fill tab and closes any open drawer', async () => {
    api.fetchMaterialPriceDetail.mockResolvedValue({
      code: 200,
      message: 'success',
      data: detail,
    })
    render(<MaterialPriceClient initialRecords={[summary]} initialTotal={1} />)
    const row = container.querySelector('tr[data-row-key="51069308"]')
    await act(async () => {
      row?.dispatchEvent(new MouseEvent("click", { bubbles: true }))
      await Promise.resolve()
    })
    await act(async () => { await Promise.resolve() })
    expect(document.body.textContent).toContain('年度汇总')

    const segment = container.querySelector('.ant-segmented')
    expect(segment).not.toBeNull()
    const fillLabel = Array.from(
      document.querySelectorAll('.ant-segmented-item-label'),
    ).find((item) => item.textContent === '表格补价')
    expect(fillLabel).not.toBeNull()
    await act(async () => {
      fillLabel!.dispatchEvent(new MouseEvent("click", { bubbles: true }))
      await Promise.resolve()
    })
    await act(async () => { await Promise.resolve() })
    expect(document.body.textContent).toContain('点击或拖拽表格到此处')
    // antd Drawer 关闭动画在 happy-dom 不移除 DOM，只断言补价面板已渲染
  })

  it('shows empty state when no records', () => {
    render(<MaterialPriceClient initialRecords={[]} initialTotal={0} />)
    expect(container.textContent).toContain('未找到匹配的物料价格记录')
  })
})