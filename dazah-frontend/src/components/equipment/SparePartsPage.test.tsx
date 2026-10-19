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
  min_qty: 5, current_qty: 20, is_active: true,
  created_at: '', updated_at: '', created_by: null, updated_by: null,
}

const warning: StockWarning = {
  spare_part_id: 'sp-2', code: 'BJ-002', name: '密封圈',
  current_qty: 2, min_qty: 10,
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
            workshopLabel="201-1 车间"
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
    expect(text).toContain('1 个备件库存低于最低库存')
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
