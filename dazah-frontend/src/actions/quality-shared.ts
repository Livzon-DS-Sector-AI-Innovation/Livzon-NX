import { getAuthHeaders } from '@/lib/auth'

export const API_BASE_URL =
  process.env.API_BASE_URL ||
  process.env.INTERNAL_API_BASE_URL ||
  'http://dazah-backend-app-1:8000'

export async function actionFetch<T>(url: string, options?: RequestInit): Promise<T | null> {
  const authHeaders = await getAuthHeaders()
  if (options?.body instanceof FormData) delete authHeaders['Content-Type']
  const response = await fetch(url, {
    ...options,
    headers: {
      ...authHeaders,
      ...options?.headers,
    },
  })
  if (!response.ok) {
    const errorBody = await response.text().catch(() => '')
    let errorMessage = `请求失败: ${response.status} ${response.statusText}`
    try {
      const errorJson = JSON.parse(errorBody)
      if (errorJson.detail) errorMessage = typeof errorJson.detail === 'string' ? errorJson.detail : JSON.stringify(errorJson.detail)
      else if (errorJson.message) errorMessage = errorJson.message
    } catch {}
    throw new Error(errorMessage)
  }
  if (response.status === 204) return null
  const result = await response.json()
  return result.data
}
