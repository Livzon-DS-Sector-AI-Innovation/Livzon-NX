import { describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ fetchSuppliers: vi.fn(), getAuthHeaders: vi.fn() }))
vi.mock('@/lib/api/purchasing', () => ({ fetchSuppliers: mocks.fetchSuppliers }))
vi.mock('@/lib/auth', () => ({ getAuthHeaders: mocks.getAuthHeaders }))
vi.mock('@/components/purchasing', () => ({ SupplierManagementClient: () => null }))

import SupplierManagementPage from './page'

describe('supplier list URL', () => {
  it('uses the URL filters and pagination for the first server request', async () => {
    mocks.getAuthHeaders.mockResolvedValue({ Authorization: 'test' })
    mocks.fetchSuppliers.mockResolvedValue({ data: [], meta: { total: 0, columns: [] } })
    await SupplierManagementPage({ searchParams: Promise.resolve({
      page: '2', page_size: '50', keyword: '原料', supplier_name: '甲公司', purchase_category: '原辅料',
    }) })
    expect(mocks.fetchSuppliers).toHaveBeenCalledWith({
      page: 2, page_size: 50, keyword: '原料', supplier_name: '甲公司',
      material_name: undefined, purchase_category: '原辅料',
    }, { Authorization: 'test' })
  })
})
