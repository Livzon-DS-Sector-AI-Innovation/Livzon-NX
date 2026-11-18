/* @vitest-environment happy-dom */

import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { App as AntApp } from 'antd'
import { describe, expect, it, vi } from 'vitest'
import { createProduct } from '@/actions/product'
import { fetchProducts } from '@/lib/api/product'
import ProductClient from './ProductClient'

vi.mock('@/actions/product', () => ({ createProduct: vi.fn(), updateProduct: vi.fn() }))
vi.mock('@/lib/api/product', () => ({ fetchProducts: vi.fn(), syncProductsFromFeishu: vi.fn() }))

describe('product migrated component contract', () => {
  it('keeps the product ledger client and its server-action boundary', () => {
    const sourcePath = resolve('src/components/product/ProductClient.tsx')
    const source = readFileSync(sourcePath, 'utf8')

    expect(existsSync(sourcePath)).toBe(true)
    expect(source).toContain('export default function ProductClient')
    expect(source).toContain("@/actions/product")
    expect(source).toContain("@/lib/api/product")
  })

  it('keeps input and shows permission feedback, then closes on successful save', async () => {
    vi.mocked(fetchProducts).mockResolvedValue({
      code: 200, message: 'ok', data: [], meta: { page: 1, page_size: 20, total: 0 },
    })
    vi.mocked(createProduct)
      .mockResolvedValueOnce({ ok: false, message: '没有执行此操作的权限，请联系管理员' })
      .mockResolvedValueOnce({ ok: true, data: {} })
    const container = document.createElement('div')
    document.body.append(container)
    const root = createRoot(container)
    const click = async (label: RegExp) => {
      const button = [...document.querySelectorAll('button')]
        .find(candidate => label.test(candidate.textContent ?? ''))
      expect(button).toBeDefined()
      await act(async () => button?.click())
    }
    try {
      await act(async () => root.render(<AntApp><ProductClient initialProducts={[]} initialTotal={0} /></AntApp>))
      await click(/新增产品/)
      const input = document.querySelector<HTMLInputElement>('input[placeholder="请输入产品名称"]')
      expect(input).not.toBeNull()
      await act(async () => {
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(input, '测试产品')
        input?.dispatchEvent(new Event('input', { bubbles: true }))
      })
      await click(/确\s*定|OK/)
      expect(createProduct).toHaveBeenCalledWith(expect.objectContaining({ name: '测试产品' }))
      await vi.waitFor(() => expect(document.body.textContent).toContain('没有执行此操作的权限，请联系管理员'))
      expect(document.querySelector('[role="dialog"]')).not.toBeNull()
      expect(input?.value).toBe('测试产品')
      expect(fetchProducts).toHaveBeenCalledTimes(1)

      await click(/确\s*定|OK/)
      await vi.waitFor(() => expect(document.body.textContent).toContain('新增成功'))
      expect(fetchProducts).toHaveBeenCalledTimes(2)
    } finally {
      await act(async () => root.unmount())
      container.remove()
    }
  })
})
