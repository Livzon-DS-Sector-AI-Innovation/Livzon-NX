/* @vitest-environment happy-dom */
import React, { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const drawerState = vi.hoisted(() => ({ open: false }))
const drawerProps = vi.hoisted(() => ({ current: null as { onSuccess?: () => void } | null }))

const mocks = vi.hoisted(() => ({
  fetchOotLimitProducts: vi.fn(),
  fetchOotLimitItems: vi.fn(),
  fetchOotLimitProductExport: vi.fn(),
  fetchOotLimitProductsExportAll: vi.fn(),
  createOotLimitProduct: vi.fn(),
  createOotLimitItem: vi.fn(),
  updateOotLimitProduct: vi.fn(),
  updateOotLimitItem: vi.fn(),
  deleteOotLimitProduct: vi.fn(),
  deleteOotLimitItem: vi.fn(),
}))

vi.mock('@/lib/api/client/quality', () => ({
  fetchOotLimitProducts: mocks.fetchOotLimitProducts,
  fetchOotLimitItems: mocks.fetchOotLimitItems,
  fetchOotLimitProductExport: mocks.fetchOotLimitProductExport,
  fetchOotLimitProductsExportAll: mocks.fetchOotLimitProductsExportAll,
}))

vi.mock('@/actions/quality', () => ({
  createOotLimitProduct: mocks.createOotLimitProduct,
  createOotLimitItem: mocks.createOotLimitItem,
  updateOotLimitProduct: mocks.updateOotLimitProduct,
  updateOotLimitItem: mocks.updateOotLimitItem,
  deleteOotLimitProduct: mocks.deleteOotLimitProduct,
  deleteOotLimitItem: mocks.deleteOotLimitItem,
}))

vi.mock('./OotLimitImportDrawer', () => ({
  OotLimitImportDrawer: (props: { isOpen: boolean; onSuccess?: () => void }) => {
    drawerState.open = props.isOpen
    drawerProps.current = props
    return null
  },
}))

import OotLimitManagementPage from './OotLimitManagementPage'

const product = {
  id: 'product-1',
  product_code: 'OOT-2026-01',
  product_name: '洛伐他汀',
  document_title: '2026年 洛伐他汀 产品OOT限度通知单',
  document_year: 2026,
  version_label: null,
  source_file_name: '2026年 LV OOT限度告知单.docx',
  remark: null,
}

const item = {
  id: 'item-1',
  product_id: 'product-1',
  display_order: 1,
  item_group: null,
  item_name: '比旋度',
  standard_value: '+324°～+338°',
  oot_limit_value: '+324°～+331°',
  remark: null,
}

let root: Root
let container: HTMLDivElement
let originalCreateObjectURL: typeof URL.createObjectURL | undefined
let originalRevokeObjectURL: typeof URL.revokeObjectURL | undefined

beforeEach(() => {
  mocks.fetchOotLimitProducts.mockReset().mockResolvedValue({ data: [product], meta: { total: 1 } })
  mocks.fetchOotLimitItems.mockReset().mockResolvedValue({ data: [item], meta: { total: 1 } })
  mocks.fetchOotLimitProductExport.mockReset()
  mocks.fetchOotLimitProductsExportAll.mockReset()
  for (const key of ['createOotLimitProduct', 'createOotLimitItem', 'updateOotLimitProduct', 'updateOotLimitItem', 'deleteOotLimitProduct', 'deleteOotLimitItem'] as const) {
    mocks[key].mockReset()
  }
  container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
  drawerState.open = false
  originalCreateObjectURL = URL.createObjectURL
  originalRevokeObjectURL = URL.revokeObjectURL
  ;(URL as unknown as Record<string, unknown>).createObjectURL = vi.fn(() => 'blob:mock')
  ;(URL as unknown as Record<string, unknown>).revokeObjectURL = vi.fn()
})

afterEach(async () => {
  await act(async () => root.unmount())
  container.remove()
  ;(URL as unknown as Record<string, unknown>).createObjectURL = originalCreateObjectURL
  ;(URL as unknown as Record<string, unknown>).revokeObjectURL = originalRevokeObjectURL
})

async function renderPage() {
  await act(async () => root.render(<App><OotLimitManagementPage /></App>))
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 30)) })
}

function findButton(label: string): HTMLButtonElement | undefined {
  return Array.from(container.querySelectorAll('button')).find((button) =>
    button.textContent?.includes(label)
  )
}

it('renders products, limit items and import/export buttons', async () => {
  await renderPage()
  expect(container.textContent).toContain('洛伐他汀')
  expect(container.textContent).toContain('比旋度')
  expect(container.textContent).toContain('+324°～+331°')
  for (const label of ['导入告知单', '导出当前产品', '导出全部']) {
    expect(findButton(label)).toBeDefined()
  }
})

it('opens the multi-file import drawer', async () => {
  await renderPage()
  expect(drawerState.open).toBe(false)
  await act(async () => findButton('导入告知单')?.click())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)) })
  expect(drawerState.open).toBe(true)
})

it('exports the selected product notice as docx', async () => {
  mocks.fetchOotLimitProductExport.mockResolvedValue({
    blob: new Blob(['docx-bytes']),
    filename: '2026年 LV OOT限度告知单.docx',
  })
  await renderPage()
  await act(async () => findButton('导出当前产品')?.click())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)) })
  expect(mocks.fetchOotLimitProductExport).toHaveBeenCalledWith('product-1')
  expect(URL.createObjectURL).toHaveBeenCalledWith(expect.any(Blob))
})

it('shows an error when exporting the current product fails', async () => {
  mocks.fetchOotLimitProductExport.mockRejectedValue(new Error('单产品导出失败'))
  await renderPage()
  await act(async () => findButton('导出当前产品')?.click())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)) })
  expect(document.body.textContent).toContain('单产品导出失败')
})

it('exports all notices as zip without needing a selection', async () => {
  mocks.fetchOotLimitProductsExportAll.mockResolvedValue({
    blob: new Blob(['zip-bytes']),
    filename: 'OOT限度告知单.zip',
  })
  await renderPage()
  await act(async () => findButton('导出全部')?.click())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)) })
  expect(mocks.fetchOotLimitProductsExportAll).toHaveBeenCalledTimes(1)
  expect(URL.createObjectURL).toHaveBeenCalled()
})

it('shows an error message when export fails', async () => {
  mocks.fetchOotLimitProductsExportAll.mockRejectedValue(new Error('暂无可导出的OOT限度产品'))
  await renderPage()
  await act(async () => findButton('导出全部')?.click())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)) })
  // antd message 渲染在 body portal 中
  expect(document.body.textContent).toContain('暂无可导出的OOT限度产品')
})
it('refreshes the product list after a successful import', async () => {
  mocks.fetchOotLimitProducts.mockClear()
  await act(async () => {
    drawerProps.current?.onSuccess?.()
    await new Promise((resolve) => setTimeout(resolve, 20))
  })
  expect(mocks.fetchOotLimitProducts).toHaveBeenCalled()
})
