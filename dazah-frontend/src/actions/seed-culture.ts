'use server'

import { revalidatePath } from 'next/cache'
import { getAuthHeaders } from '@/lib/auth'
import type { SeedCultureRecord, SeedCultureCreate, SeedCultureUpdate } from '@/types/seed-culture'
import type { ApiResponse } from '@/types/production'

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'

async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<ApiResponse<T>> {
  const authHeaders = await getAuthHeaders()
  const { headers: optHeaders, ...restOptions } = options || {}
  const response = await fetch(`${API_BASE}${endpoint}`, {
    headers: { ...authHeaders, ...optHeaders },
    ...restOptions,
  })
  return response.json()
}

export async function getSeedCultures(params: { page?: number; page_size?: number; batch_no?: string; product_name?: string } = {}) {
  const sp = new URLSearchParams()
  if (params.page) sp.set('page', String(params.page))
  if (params.page_size) sp.set('page_size', String(params.page_size))
  if (params.batch_no) sp.set('batch_no', params.batch_no)
  if (params.product_name) sp.set('product_name', params.product_name)
  const qs = sp.toString()
  return fetchApi<SeedCultureRecord[]>(`/api/v1/production/seed-cultures${qs ? `?${qs}` : ''}`)
}

export async function createSeedCulture(data: SeedCultureCreate) {
  const res = await fetchApi<SeedCultureRecord>('/api/v1/production/seed-cultures', {
    method: 'POST', body: JSON.stringify(data),
  })
  revalidatePath('/production/batches/workshop/101-1')
  return res
}

export async function updateSeedCulture(id: string, data: SeedCultureUpdate) {
  const res = await fetchApi<SeedCultureRecord>(`/api/v1/production/seed-cultures/${id}`, {
    method: 'PUT', body: JSON.stringify(data),
  })
  revalidatePath('/production/batches/workshop/101-1')
  return res
}

export async function deleteSeedCulture(id: string) {
  const res = await fetchApi<null>(`/api/v1/production/seed-cultures/${id}`, { method: 'DELETE' })
  revalidatePath('/production/batches/workshop/101-1')
  return res
}
