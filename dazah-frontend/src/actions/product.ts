'use server'

import { getServerApiBaseUrl } from '@/lib/server-api'
import { revalidatePath } from 'next/cache'
import { ProductCreateInput, ProductUpdateInput } from '@/types/product'

const API_BASE = getServerApiBaseUrl()

export async function createProduct(data: ProductCreateInput) {
  const res = await fetch(`${API_BASE}/api/v1/product/products`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || '创建产品失败')
  }
  revalidatePath('/production/products')
  return res.json()
}

export async function updateProduct(id: string, data: ProductUpdateInput) {
  const res = await fetch(`${API_BASE}/api/v1/product/products/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || '更新产品失败')
  }
  revalidatePath('/production/products')
  return res.json()
}

export async function deleteProduct(id: string) {
  const res = await fetch(`${API_BASE}/api/v1/product/products/${id}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || '删除产品失败')
  }
  revalidatePath('/production/products')
  return res.json()
}
