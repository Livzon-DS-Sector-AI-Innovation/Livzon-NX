/* @vitest-environment happy-dom */

import { renderToStaticMarkup } from 'react-dom/server'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import DocumentCatalogPage from './DocumentCatalogPage'

const flags = vi.hoisted(() => ({ canOperate: false, canDelete: false, canExport: false, canImport: false }))
vi.mock('@/hooks/usePagePermissions', () => ({ usePagePermissions: () => flags }))
vi.mock('@/actions/quality', () => ({
  createDocumentDepartment: vi.fn(), createDocumentEntry: vi.fn(),
  deleteDocumentDepartment: vi.fn(), deleteDocumentEntry: vi.fn(),
  importDocumentCatalogExcel: vi.fn(), batchImportDocumentAttachments: vi.fn(),
  updateDocumentDepartment: vi.fn(), updateDocumentEntry: vi.fn(), deleteDocumentEntryAttachment: vi.fn(),
}))
vi.mock('@/lib/api/client/quality', () => ({
  fetchDocumentDepartments: vi.fn(), fetchDocumentEntries: vi.fn(),
  fetchDocumentCatalogExport: vi.fn(), fetchDocumentEntryAttachmentContent: vi.fn(),
}))

describe('document catalog page actions', () => {
  it.each([
    { operate: false, sensitive: false },
    { operate: true, sensitive: false },
    { operate: true, sensitive: true },
  ])('enforces independent actions: %j', ({ operate, sensitive }) => {
    Object.assign(flags, { canOperate: operate, canDelete: sensitive, canImport: sensitive, canExport: sensitive })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    client.setQueryData(['quality-documents', 'entries', 'all', '', 1, 50], {
      items: [{ id: 'entry', department_id: 'dept', name: '验收文件', attachments: [] }], total: 1,
    })
    const container = document.createElement('div')
    container.innerHTML = renderToStaticMarkup(
      <QueryClientProvider client={client}>
        <DocumentCatalogPage initialDepartments={[{ id: 'dept', name: '验收部门', sort_order: 1, document_count: 1, created_at: '', updated_at: '' }]} />
      </QueryClientProvider>,
    )
    const button = (label: string) => {
      const found = Array.from(container.querySelectorAll('button')).find(item => item.textContent?.replace(/\s/g, '') === label)
      expect(found, label).toBeDefined()
      return found!
    }
    expect(button('新增条目').disabled).toBe(!operate)
    expect(button('编辑').disabled).toBe(!operate)
    for (const label of ['删除', '导入文件目录', '导入附件', '导出']) {
      expect(button(label).disabled).toBe(!sensitive)
    }
    client.clear()
  })
})
