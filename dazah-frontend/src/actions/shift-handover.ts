'use server'

import { revalidatePath } from 'next/cache'
import { getAuthHeaders } from '@/lib/auth'
import type { ShiftHandoverRecord, ShiftHandoverCreate, ShiftHandoverUpdate } from '@/types/shift-handover'
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

export async function getShiftHandovers(params: {
  page?: number
  page_size?: number
  position?: string
  workshop?: string
  date_from?: string
  date_to?: string
} = {}) {
  const sp = new URLSearchParams()
  if (params.page) sp.set('page', String(params.page))
  if (params.page_size) sp.set('page_size', String(params.page_size))
  if (params.position) sp.set('position', params.position)
  if (params.workshop) sp.set('workshop', params.workshop)
  if (params.date_from) sp.set('date_from', params.date_from)
  if (params.date_to) sp.set('date_to', params.date_to)
  const qs = sp.toString()
  return fetchApi<ShiftHandoverRecord[]>(`/api/v1/production/shift-handovers${qs ? `?${qs}` : ''}`)
}

export async function getShiftHandover(id: string) {
  return fetchApi<ShiftHandoverRecord>(`/api/v1/production/shift-handovers/${id}`)
}

export async function createShiftHandover(data: ShiftHandoverCreate) {
  const res = await fetchApi<ShiftHandoverRecord>('/api/v1/production/shift-handovers', {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/production/shift-log/handover')
  return res
}

export async function updateShiftHandover(id: string, data: ShiftHandoverUpdate) {
  const res = await fetchApi<ShiftHandoverRecord>(`/api/v1/production/shift-handovers/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath('/production/shift-log/handover')
  return res
}

export async function deleteShiftHandover(id: string) {
  const res = await fetchApi<null>(`/api/v1/production/shift-handovers/${id}`, {
    method: 'DELETE',
  })
  revalidatePath('/production/shift-log/handover')
  return res
}

export async function confirmShiftHandover(id: string) {
  const res = await fetchApi<ShiftHandoverRecord>(`/api/v1/production/shift-handovers/${id}/confirm`, {
    method: 'POST',
  })
  revalidatePath('/production/shift-log/handover')
  return res
}

export async function getDistinctPositions() {
  return fetchApi<string[]>('/api/v1/production/shift-handovers/positions')
}
