/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiClient = vi.hoisted(() => ({
  fetchSupplierQualifications: vi.fn(),
  searchChangeActionPlanPersons: vi.fn(),
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

  it('editing a record keeps responsible_users pre-filled and saves them back', async () => {
    apiClient.fetchSupplierQualifications.mockResolvedValue({
      items: [
        {
          record_id: 'r1',
          supplier_name: '南平元力活性炭',
          material_name: null,
          material_type: '固体',
          qualification_name: '营业执照',
          qualification_file: null,
          is_completed: false,
          deadline: null,
          responsible_person: '甄宁宁',
          responsible_users: [{ id: 'ou_edit_001', name: '甄宁宁' }],
          groups: [{ id: 'oc_group_1', name: '供应商资质沟通群', avatar_url: '' }],
          remark: null,
          expiry_status: '正常',
          created_at: '2026-09-01T00:00:00Z',
          updated_at: '2026-09-01T00:00:00Z',
        },
      ],
      total: 1,
    })
    qualityActions.updateSupplierQualification.mockResolvedValue({})
    await renderPage()

    // 列表渲染：负责人列带头像+姓名、群组列带群名
    expect(container.textContent).toContain('甄宁宁')
    expect(container.textContent).toContain('供应商资质沟通群')

    // 打开编辑弹窗（操作列「修改」按钮）
    const editButton = Array.from(container.querySelectorAll('button')).find(
      (node) => (node.textContent || '').includes('修改'),
    ) as HTMLElement | undefined
    expect(editButton).toBeTruthy()
    await act(async () => {
      editButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 80))
    })

    // 编辑弹窗中负责人已预选（多选标签）
    expect(document.body.textContent).toContain('甄宁宁')

    // 直接提交，保存 payload 应带 responsible_users
    const okButton = document.body.querySelector(
      '.ant-modal .ant-btn-primary',
    ) as HTMLElement | null
    expect(okButton).toBeTruthy()
    await act(async () => {
      okButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 200))
    })

    expect(qualityActions.updateSupplierQualification).toHaveBeenCalledWith(
      'r1',
      expect.objectContaining({
        responsible_users: [{ id: 'ou_edit_001', name: '甄宁宁' }],
      }),
    )
  })
})
