/* @vitest-environment happy-dom */
import { renderToStaticMarkup } from 'react-dom/server'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import ProductQualityStandardPage from './ProductQualityStandardPage'
import SupplierQualificationPage from './SupplierQualificationPage'

const flags = vi.hoisted(() => ({ canOperate: false, canDelete: false, canSync: false }))
vi.mock('@/hooks/usePagePermissions', () => ({ usePagePermissions: () => flags }))
vi.mock('@/actions/quality', () => ({
  createProductQualityStandardAction: vi.fn(), updateProductQualityStandardAction: vi.fn(),
  deleteProductQualityStandardAction: vi.fn(), pullProductQualityStandardsAction: vi.fn(),
  createSupplierQualification: vi.fn(), updateSupplierQualification: vi.fn(),
  deleteSupplierQualification: vi.fn(), pullSupplierQualifications: vi.fn(),
}))
vi.mock('@/lib/api/client/quality', () => ({
  fetchProductQualityStandards: vi.fn(), fetchSupplierQualifications: vi.fn(),
  searchChangeActionPlanPersons: vi.fn(),
}))

describe('shared quality ledgers', () => {
  it.each([false, true])('keeps sync separate from edit permission: %s', (canOperate) => {
    Object.assign(flags, { canOperate, canDelete: false, canSync: false })
    for (const page of [<ProductQualityStandardPage key="product" productCode="mfn" productLabel="霉酚酸" />, <SupplierQualificationPage key="supplier" />]) {
      const client = new QueryClient()
      const container = document.createElement('div')
      container.innerHTML = renderToStaticMarkup(<QueryClientProvider client={client}>{page}</QueryClientProvider>)
      const buttons = Array.from(container.querySelectorAll('button'))
      const add = buttons.find(button => button.textContent?.replace(/\s/g, '') === '新增')
      const sync = buttons.find(button => button.textContent?.replace(/\s/g, '') === '从飞书拉取')
      expect(add).toBeDefined()
      expect(sync).toBeDefined()
      expect(add!.disabled).toBe(!canOperate)
      expect(sync!.disabled).toBe(true)
      client.clear()
    }
  })
})
