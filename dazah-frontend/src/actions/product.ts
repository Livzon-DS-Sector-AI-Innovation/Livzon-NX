'use server'

import { getServerApiBaseUrl } from '@/lib/server-api'
import { revalidatePath } from 'next/cache'
import { getAuthHeaders } from '@/lib/auth'
import { requireActionResponse, serverActionResult } from '@/lib/server-action-result'
import { uncertainWriteMessage } from '@/lib/user-error'
import type { components } from '@/types/generated/schema'

const API_BASE = getServerApiBaseUrl()

function mutateProduct(operation: string, label: string, path: string, init: RequestInit) {
  return serverActionResult(`product.${operation}`, async (): Promise<unknown> => {
    const response = await fetch(`${API_BASE}/api/v1/product/products${path}`, {
      ...init,
      headers: await getAuthHeaders(),
    })
    await requireActionResponse(response)
    const payload: unknown = await response.json()
    revalidatePath('/production/products')
    return payload
  }, uncertainWriteMessage(label))
}

export async function createProduct(data: components['schemas']['ProductCreate']) {
  return mutateProduct('create', '产品创建', '', { method: 'POST', body: JSON.stringify(data) })
}

export async function updateProduct(id: string, data: components['schemas']['ProductUpdate']) {
  return mutateProduct('update', '产品更新', `/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export async function deleteProduct(id: string) {
  return mutateProduct('delete', '产品删除', `/${encodeURIComponent(id)}`, { method: 'DELETE' })
}
