'use server'

import { getServerApiBaseUrl } from '@/lib/server-api'
import { getAuthHeaders } from '@/lib/auth'
import type { components } from '@/types/generated/schema'

const API_BASE = getServerApiBaseUrl()

export type LLMConfig = components['schemas']['LLMConfigResponse']
export type LLMConfigFormData = components['schemas']['LLMConfigCreate']
export type LLMConfigUpdate = components['schemas']['LLMConfigUpdate']
export type LLMCapabilityDetection = components['schemas']['LLMCapabilityDetectionResponse']
export type FeishuConfig = components['schemas']['FeishuConfigResponse']
export type FeishuConfigUpsert = components['schemas']['FeishuConfigUpsert']
export type FeishuDiagnosticResult = components['schemas']['FeishuDiagnosticResult']
export type LivzonFeishuEventWsStatus = components['schemas']['LivzonFeishuEventWsStatus']

interface ApiResponse<T> {
  code: number
  data: T
  message?: string
}

function getErrorMessage(value: unknown, fallback: string): string {
  if (!value || typeof value !== 'object') return fallback
  const payload = value as { detail?: unknown; message?: unknown }
  if (typeof payload.detail === 'string' && payload.detail) return payload.detail
  if (typeof payload.message === 'string' && payload.message) return payload.message
  return fallback
}

async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<ApiResponse<T>> {
  const authHeaders = await getAuthHeaders()

  const res = await fetch(`${API_BASE}/api/v1${endpoint}`, {
    ...options,
    headers: {
      ...authHeaders,
      ...options?.headers,
    },
    cache: 'no-store',
  })

  if (!res.ok) {
    const fallback = `API error: ${res.status}`
    const errorText = await res.text()
    if (!errorText) {
      throw new Error(fallback)
    }
    try {
      throw new Error(getErrorMessage(JSON.parse(errorText), fallback))
    } catch (error) {
      if (error instanceof SyntaxError) {
        throw new Error(errorText)
      }
      throw error
    }
  }

  if (res.status === 204) {
    return { code: 0, data: null as T }
  }

  const data = await res.json()
  return { code: 0, data }
}

export async function getLLMConfigs(configType?: string) {
  const searchParams = new URLSearchParams()
  if (configType) searchParams.set('config_type', configType)

  const queryString = searchParams.toString()
  const endpoint = `/llm/configs${queryString ? `?${queryString}` : ''}`
  return fetchApi<LLMConfig[]>(endpoint)
}

export async function getLLMConfig(id: string) {
  return fetchApi<LLMConfig>(`/llm/configs/${id}`)
}

export async function createLLMConfig(data: LLMConfigFormData) {
  const response = await fetchApi<LLMConfig>('/llm/configs', {
    method: 'POST',
    body: JSON.stringify(data),
  })
  return response
}

export async function updateLLMConfig(id: string, data: LLMConfigUpdate) {
  const response = await fetchApi<LLMConfig>(`/llm/configs/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  return response
}

export async function deleteLLMConfig(id: string) {
  const response = await fetchApi<null>(`/llm/configs/${id}`, {
    method: 'DELETE',
  })
  return response
}

export async function testLLMConnection() {
  const response = await fetchApi<LLMCapabilityDetection>('/llm/configs/test', {
    method: 'POST',
  })
  return response
}

export async function testLLMConfig(id: string) {
  return fetchApi<LLMCapabilityDetection>(`/llm/configs/${id}/test`, {
    method: 'POST',
  })
}

function unwrapResponseData<T>(value: unknown): T {
  if (
    value &&
    typeof value === 'object' &&
    'data' in value
  ) {
    return (value as { data: T }).data
  }
  return value as T
}

export async function getLivzonFeishuConfig() {
  const response = await fetchApi<unknown>('/identity/feishu-config')
  return unwrapResponseData<FeishuConfig>(response.data)
}

export async function saveLivzonFeishuConfig(data: FeishuConfigUpsert) {
  const response = await fetchApi<unknown>('/identity/feishu-config', {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  return unwrapResponseData<FeishuConfig>(response.data)
}

export async function testLivzonFeishuConfig(data?: FeishuConfigUpsert) {
  const response = await fetchApi<unknown>('/identity/feishu-config/test', {
    method: 'POST',
    body: JSON.stringify(data || null),
  })
  return unwrapResponseData<FeishuDiagnosticResult>(response.data)
}

export async function syncLivzonFeishuContacts() {
  const response = await fetchApi<unknown>('/identity/sync/all', {
    method: 'POST',
  })
  return unwrapResponseData<{
    message?: string
    status?: string
    departments?: Record<string, unknown>
    members?: Record<string, unknown>
  }>(response.data)
}

export async function getLivzonFeishuEventWsStatus() {
  const response = await fetchApi<unknown>('/identity/feishu/event-ws/status')
  return unwrapResponseData<LivzonFeishuEventWsStatus>(response.data)
}

export async function restartLivzonFeishuEventWs() {
  const response = await fetchApi<unknown>('/identity/feishu/event-ws/restart', {
    method: 'POST',
  })
  return unwrapResponseData<LivzonFeishuEventWsStatus>(response.data)
}
