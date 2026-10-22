/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App as AntApp, ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  fetchSparePartsClient: vi.fn(),
  fetchStockWarningsClient: vi.fn(),
}))

const drawerProps: Array<Record<string, unknown>> = []
vi.mock('./SparePartDrawer', () => ({
  SparePartDrawer: (props: Record<string, unknown>) => {
    drawerProps.push(props)
    return null
  },
}))
vi.mock('./StockInboundDrawer', () => ({
  StockInboundDrawer: (props: Record<string, unknown>) => {
    drawerProps.push(props)
    return null
  },
}))

vi.mock('@/lib/api/equipment-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api/equipment-client')>()
  return { ...actual, ...api }
})

import { SparePartsPage } from './SparePartsPage'
import { useEquipmentStore } from '@/stores/equipment'
import type { SparePart, StockWarning } from '@/types/equipment'

const sparePart: SparePart = {
  id: 'sp-1', code: 'BJ-001', name: '滤芯', specification: null,
  unit: '个', category: null, default_supplier: null, unit_price: null,
  workshop_code: '201-1', safety_qty: 5, current_qty: 20, is_active: true,
  created_at: '', updated_at: '', created_by: null, updated_by: null,
}

const warning: StockWarning = {
  spare_part: { ...sparePart, id: 'sp-2', code: 'BJ-002', name: '密封圈' },
  stock: {
    id: 'stock-2', spare_part_id: 'sp-2', warehouse_location: null,
    current_qty: 2, safety_qty: 10, min_order_qty: 1,
  },
  shortage: 8,
}

let root: Root | null = null

function renderPage(warnings: StockWarning[]) {
  const container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  api.fetchSparePartsClient.mockResolvedValue({ items: [sparePart], total: 1, page: 1, page_size: 20 })
  api.fetchStockWarningsClient.mockResolvedValue(warnings)
  act(() => {
    root!.render(
      <ConfigProvider locale={zhCN}>
        <AntApp>
          <SparePartsPage
            workshopCode="201-1"
            initialSpareParts={[sparePart]}
            initialSparePartTotal={1}
            initialStockWarnings={warnings}
          />
        </AntApp>
      </ConfigProvider>,
    )
  })
}

beforeEach(() => {
  drawerProps.length = 0
  useEquipmentStore.setState({
    sparePartPage: 1,
    sparePartPageSize: 20,
    sparePartKeyword: '',
  })
})

afterEach(() => {
  act(() => root?.unmount())
  document.body.innerHTML = ''
  useEquipmentStore.setState({ stockWarnings: [] })
  vi.clearAllMocks()
})

describe('SparePartsPage 库存预警', () => {
  it('存在低于最低库存的备件时展示预警区', async () => {
    renderPage([warning])
    await act(async () => { await new Promise((r) => setTimeout(r, 0)) })

    const text = document.body.textContent || ''
    // 预警提示条 + 预警行（副标题常含“库存预警”字样，以数据断言为准）
    expect(text).toContain('1 个备件库存低于安全库存')
    expect(text).toContain('BJ-002')
  })

  it('无预警时不渲染预警区', async () => {
    renderPage([])
    await act(async () => { await new Promise((r) => setTimeout(r, 0)) })

    const text = document.body.textContent || ''
    expect(text).not.toContain('个备件库存低于最低库存')
    expect(text).not.toContain('BJ-002')
    expect(text).toContain('BJ-001')
  })
})

describe('SparePartsPage 数据流', () => {
  it('翻页后按新页码重新请求列表', async () => {
    // 25 条数据使第二页按钮出现（独立 root，避免复用已卸载实例）
    api.fetchSparePartsClient.mockResolvedValue({ items: [], total: 25, page: 2, page_size: 20 })
    const myContainer = document.createElement('div')
    document.body.append(myContainer)
    const myRoot = createRoot(myContainer)
    await act(async () => {
      myRoot.render(
        <ConfigProvider locale={zhCN}>
          <AntApp>
            <SparePartsPage
              workshopCode="201-1"
              initialSpareParts={[]}
              initialSparePartTotal={25}
              initialStockWarnings={[]}
            />
          </AntApp>
        </ConfigProvider>,
      )
      await Promise.resolve()
    })
    api.fetchSparePartsClient.mockClear()
    const page2 = document.querySelector('.ant-pagination-item-2')
    expect(page2).not.toBeNull()
    await act(async () => {
      ;(page2 as HTMLElement).click()
      await Promise.resolve()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    expect(api.fetchSparePartsClient).toHaveBeenCalledWith(
      expect.objectContaining({ page: 2, page_size: 20, workshop: '201-1' }),
    )
    act(() => myRoot.unmount())
    myContainer.remove()
  })

  it('抽屉提交后触发刷新且页面保持可用', async () => {
    renderPage([])
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
    const drawer = drawerProps.find((props) => typeof props.onRefresh === 'function') as
      | { onRefresh: () => void }
      | undefined
    expect(drawer).toBeDefined()
    // 回调执行 invalidate 不抛错，且渲染数据仍由查询缓存供出
    await act(async () => {
      drawer!.onRefresh()
      await Promise.resolve()
      await Promise.resolve()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    expect(document.body.textContent || '').toContain('BJ-001')
  })
})
