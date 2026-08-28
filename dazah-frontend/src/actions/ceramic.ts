'use server'

import { revalidatePath } from 'next/cache'
import { getAuthHeaders } from '@/lib/auth'
import type { ApiResponse } from '@/types/production'

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'

async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<ApiResponse<T>> {
  const authHeaders = await getAuthHeaders()
  const r = await fetch(`${API_BASE}${endpoint}`, { headers: { ...authHeaders, ...options?.headers }, ...options })
  return r.json()
}

function makeCrud<T>(prefix: string, path: string) {
  return {
    list: (params: Record<string, unknown> = {}) => {
      const sp = new URLSearchParams()
      Object.entries(params).forEach(([k, v]) => { if (v) sp.set(k, String(v)) })
      return fetchApi<T[]>(`/api/v1/production/${prefix}${sp.size ? '?' + sp.toString() : ''}`)
    },
    create: async (data: Record<string, unknown>) => {
      const res = await fetchApi<T>(`/api/v1/production/${prefix}`, { method: 'POST', body: JSON.stringify(data) })
      revalidatePath(path); return res
    },
    update: async (id: string, data: Record<string, unknown>) => {
      const res = await fetchApi<T>(`/api/v1/production/${prefix}/${id}`, { method: 'PUT', body: JSON.stringify(data) })
      revalidatePath(path); return res
    },
    delete: async (id: string) => {
      const res = await fetchApi<null>(`/api/v1/production/${prefix}/${id}`, { method: 'DELETE' })
      revalidatePath(path); return res
    },
  }
}

export const ceramicFeed = makeCrud('ceramic-feeds', '/production/batches/workshop/203')
export const ceramicOps = makeCrud('ceramic-membrane-ops', '/production/batches/workshop/203')
export const ceramicClean = makeCrud('ceramic-membrane-cleans', '/production/batches/workshop/203')
export const ceramicSep = makeCrud('ceramic-material-separations', '/production/batches/workshop/203')
export const ceramicEquip = makeCrud('ceramic-equipment-logs', '/production/batches/workshop/203')
