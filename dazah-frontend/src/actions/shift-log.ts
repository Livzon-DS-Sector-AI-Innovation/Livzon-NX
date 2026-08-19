'use server'

import { revalidatePath } from 'next/cache'
import { getAuthHeaders } from '@/lib/auth'
import type { ShiftLogRecord, ShiftLogCreate, ShiftLogUpdate } from '@/types/shift-log'
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

export async function getShiftLogs(params: {
  page?: number
  page_size?: number
  workshop?: string
  shift?: string
  date_from?: string
  date_to?: string
} = {}) {
  const sp = new URLSearchParams()
  if (params.page) sp.set('page', String(params.page))
  if (params.page_size) sp.set('page_size', String(params.page_size))
  if (params.workshop) sp.set('workshop', params.workshop)
  if (params.shift) sp.set('shift', params.shift)
  if (params.date_from) sp.set('date_from', params.date_from)
  if (params.date_to) sp.set('date_to', params.date_to)
  const qs = sp.toString()
  return fetchApi<ShiftLogRecord[]>(`/api/v1/production/shift-logs${qs ? `?${qs}` : ''}`)
}

export async function getShiftLog(id: string) {
  return fetchApi<ShiftLogRecord>(`/api/v1/production/shift-logs/${id}`)
}

export async function createShiftLog(data: ShiftLogCreate) {
  const res = await fetchApi<ShiftLogRecord>('/api/v1/production/shift-logs', {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/production/shift-log/workshop')
  return res
}

export async function updateShiftLog(id: string, data: ShiftLogUpdate) {
  const res = await fetchApi<ShiftLogRecord>(`/api/v1/production/shift-logs/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath('/production/shift-log/workshop')
  return res
}

export async function deleteShiftLog(id: string) {
  const res = await fetchApi<null>(`/api/v1/production/shift-logs/${id}`, {
    method: 'DELETE',
  })
  revalidatePath('/production/shift-log/workshop')
  return res
}
