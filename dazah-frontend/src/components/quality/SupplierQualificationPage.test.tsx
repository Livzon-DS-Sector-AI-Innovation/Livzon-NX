/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiClient = vi.hoisted(() => ({
  fetchSupplierQualifications: vi.fn(),
}))

const qualityActions = vi.hoisted(() => ({
  pullSupplierQualifications: vi.fn(),
  createSupplierQualification: vi.fn(),
  updateSupplierQualification: vi.fn(),
  deleteSupplierQualification: vi.fn(),
}))

vi.mock('@/lib/api/client/quality', () => apiClient)
vi.mock('@/actions/quality', () => qualityActions)

import SupplierQualificationPage from './SupplierQualificationPage'

function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

describe('SupplierQualificationPage 到期状态筛选', () => {
  let root: Root
  let container: HTMLElement

  beforeEach(() => {
    apiClient.fetchSupplierQualifications.mockResolvedValue({ items: [], total: 0 })
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    document.body
      .querySelectorAll('.ant-modal-root, .ant-select-dropdown, .ant-message')
      .forEach((node) => node.remove())
    vi.clearAllMocks()
  })

  async function renderPage() {
    await act(async () => {
      root.render(
        <App>
          <QueryClientProvider client={makeQueryClient()}>
            <SupplierQualificationPage />
          </QueryClientProvider>
        </App>,
      )
    })
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50))
    })
  }

  it('renders the 到期状态 filter alongside the other selects', async () => {
    await renderPage()
    expect(apiClient.fetchSupplierQualifications).toHaveBeenCalled()
    const placeholders = Array.from(
      container.querySelectorAll('.ant-select-placeholder'),
    ).map((node) => node.textContent || '')
    expect(placeholders.some((text) => text.includes('到期状态'))).toBe(true)
  })

  it('re-fetches with expiry_bucket=due_30 when 30天内到期 is selected', async () => {
    await renderPage()
    apiClient.fetchSupplierQualifications.mockClear()

    const wrapper = (
      Array.from(container.querySelectorAll('.ant-select')) as HTMLElement[]
    ).find(
      (node) =>
        node
          .querySelector('.ant-select-placeholder')
          ?.textContent?.includes('到期状态'),
    )
    expect(wrapper).toBeTruthy()

    await act(async () => {
      wrapper?.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      wrapper?.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 30))
    })

    const option = Array.from(
      document.body.querySelectorAll('.ant-select-item-option'),
    ).find((node) => (node.textContent || '').includes('30天内到期'))
    expect(option).toBeTruthy()

    await act(async () => {
      option?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 100))
    })

    expect(apiClient.fetchSupplierQualifications).toHaveBeenCalledWith(
      expect.objectContaining({ expiry_bucket: 'due_30' }),
    )
  })

  it('submits the search term to the backend keyword param (server-side, not local filter)', async () => {
    await renderPage()
    apiClient.fetchSupplierQualifications.mockClear()

    const input = container.querySelector('.ant-input') as HTMLInputElement | null
    expect(input).toBeTruthy()
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      'value',
    )?.set
    await act(async () => {
      setter?.call(input, '南平')
      input?.dispatchEvent(new Event('input', { bubbles: true }))
    })

    const searchButton = container.querySelector(
      '.ant-input-search-btn',
    ) as HTMLElement | null
    expect(searchButton).toBeTruthy()
    await act(async () => {
      searchButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 100))
    })

    expect(apiClient.fetchSupplierQualifications).toHaveBeenCalledWith(
      expect.objectContaining({ keyword: '南平' }),
    )
  })

  it('shows server-side pagination with the backend total', async () => {
    apiClient.fetchSupplierQualifications.mockResolvedValue({ items: [], total: 2400 })
    await renderPage()

    expect(container.textContent).toContain('共 2400 条')
    // 分页器页码至少渲染到第 2 页（2400/20），证明不是只取前 200 条
    const pageButtons = Array.from(
      container.querySelectorAll('.ant-pagination-item'),
    ).map((node) => node.textContent)
    expect(pageButtons).toContain('2')
  })
})
