'use server'

import { revalidatePath } from 'next/cache'
import { getAuthHeaders } from '@/lib/auth'
import type { FermentationRecord, FermentationCreate, FermentationUpdate } from '@/types/fermentation'
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

export async function getFermentationRecords(params: {
  page?: number
  page_size?: number
  product_name?: string
  batch_no?: string
  status?: string
  fermenter?: string
} = {}) {
  const sp = new URLSearchParams()
  if (params.page) sp.set('page', String(params.page))
  if (params.page_size) sp.set('page_size', String(params.page_size))
  if (params.product_name) sp.set('product_name', params.product_name)
  if (params.batch_no) sp.set('batch_no', params.batch_no)
  if (params.status) sp.set('status', params.status)
  if (params.fermenter) sp.set('fermenter', params.fermenter)
  const qs = sp.toString()
  return fetchApi<FermentationRecord[]>(`/api/v1/production/fermentation${qs ? `?${qs}` : ''}`)
}

export async function getFermentationRecord(id: string) {
  return fetchApi<FermentationRecord>(`/api/v1/production/fermentation/${id}`)
}

export async function createFermentationRecord(data: FermentationCreate) {
  const res = await fetchApi<FermentationRecord>('/api/v1/production/fermentation', {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/production/batches/workshop/103')
  return res
}

export async function updateFermentationRecord(id: string, data: FermentationUpdate) {
  const res = await fetchApi<FermentationRecord>(`/api/v1/production/fermentation/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath('/production/batches/workshop/103')
  return res
}

export async function updateFermentationStatus(id: string, status: string) {
  const res = await fetchApi<FermentationRecord>(`/api/v1/production/fermentation/${id}/status`, {
    method: 'PUT',
    body: JSON.stringify({ status }),
  })
  revalidatePath('/production/batches/workshop/103')
  return res
}

export async function deleteFermentationRecord(id: string) {
  const res = await fetchApi<null>(`/api/v1/production/fermentation/${id}`, {
    method: 'DELETE',
  })
  revalidatePath('/production/batches/workshop/103')
  return res
}
