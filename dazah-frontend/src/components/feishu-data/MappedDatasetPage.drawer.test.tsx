/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const navigation = vi.hoisted(() => ({ replace: vi.fn() }))
const mappedApi = vi.hoisted(() => ({
  fetchMappedPageData: vi.fn(),
  fetchMappedPageDataset: vi.fn(),
  mappedAttachmentUrl: vi.fn(() => '/attachment'),
}))

vi.mock('next/navigation', () => ({
  useRouter: () => navigation,
  useSearchParams: () => new URLSearchParams('dataset=binding-1'),
}))
vi.mock('@/lib/api/mapped-feishu', () => mappedApi)

import { MappedDatasetPage } from './MappedDatasetPage'

let root: Root
let container: HTMLElement

beforeEach(() => {
  container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
  mappedApi.fetchMappedPageDataset.mockResolvedValue({
    fields: [{ field_id: 'detail', field_name: '附件' }],
    records: [{ record_id: 'record-1', fields: { 附件: [{ name: '报告.pdf', file_token: 'file-1' }] } }],
    pagination: { page: 1, page_size: 50, total: 1 },
  })
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
  vi.clearAllMocks()
})

it('opens mapped record details in a readable drawer with its attachment link', async () => {
  act(() => root.render(<MappedDatasetPage
    pageKey="warehouse.records"
    title="仓储记录"
    initialPageData={{ bindings: [{ id: 'binding-1', tab_label: '记录', is_default: true, table: { app_token: 'app-1' } }] }}
  />))
  await act(async () => { await mappedApi.fetchMappedPageDataset.mock.results[0]?.value })

  const detailButton = [...container.querySelectorAll('button')].find((button) => button.textContent?.includes('报告.pdf'))
  expect(detailButton).toBeTruthy()
  act(() => detailButton?.click())

  const drawer = document.body.querySelector('.ant-drawer-content-wrapper')
  expect(drawer?.getAttribute('style')).toContain('width: 720px')
  expect(drawer?.textContent).toContain('报告.pdf')
  expect(drawer?.querySelector('a')?.getAttribute('href')).toBe('/attachment')
})
