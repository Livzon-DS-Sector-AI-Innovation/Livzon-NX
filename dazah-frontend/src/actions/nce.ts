'use server'

import { revalidatePath } from 'next/cache'
import { getAuthHeaders } from '@/lib/auth'
import type { NCERecord, NCECreate, NCEUpdate } from '@/types/nce'
import type { ApiResponse } from '@/types/production'

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'

async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<ApiResponse<T>> {
  const authHeaders = await getAuthHeaders()
  const { headers: optHeaders, ...restOptions } = options || {}
  const response = await fetch(`${API_BASE}${endpoint}`, { headers: { ...authHeaders, ...optHeaders }, ...restOptions })
  return response.json()
}

export async function getNCEs(params: { page?: number; page_size?: number; workshop?: string; event_type?: string; date_from?: string; date_to?: string } = {}) {
  const sp = new URLSearchParams()
  if (params.page) sp.set('page', String(params.page))
  if (params.page_size) sp.set('page_size', String(params.page_size))
  if (params.workshop) sp.set('workshop', params.workshop)
  if (params.event_type) sp.set('event_type', params.event_type)
  if (params.date_from) sp.set('date_from', params.date_from)
  if (params.date_to) sp.set('date_to', params.date_to)
  return fetchApi<NCERecord[]>(`/api/v1/production/non-conforming-events${sp.size ? `?${sp}` : ''}`)
}

export async function createNCE(data: NCECreate) {
  const res = await fetchApi<NCERecord>('/api/v1/production/non-conforming-events', { method: 'POST', body: JSON.stringify(data) })
  revalidatePath('/production/shift-log/deviation')
  return res
}

export async function updateNCE(id: string, data: NCEUpdate) {
  const res = await fetchApi<NCERecord>(`/api/v1/production/non-conforming-events/${id}`, { method: 'PUT', body: JSON.stringify(data) })
  revalidatePath('/production/shift-log/deviation')
  return res
}

export async function deleteNCE(id: string) {
  const res = await fetchApi<null>(`/api/v1/production/non-conforming-events/${id}`, { method: 'DELETE' })
  revalidatePath('/production/shift-log/deviation')
  return res
}
