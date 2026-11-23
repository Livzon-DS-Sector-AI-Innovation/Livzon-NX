import { getAuthHeaders } from '@/lib/auth'
import { ActionRequestError, requireActionResponse, type BusinessErrorMessages } from '@/lib/server-action-result'
import type { components } from '@/types/generated/schema'

export const qualityImportErrorMessages = {
  422: { QUALITY_IMPORT_INVALID_DOCUMENT: '无法解析 Word 文档，请使用有效的 .docx 模板重新上传' },
} satisfies Record<422, Record<components['schemas']['QualityImportErrorDetail']['error_code'], string>>

export const API_BASE_URL =
  process.env.API_BASE_URL ||
  process.env.INTERNAL_API_BASE_URL ||
  'http://dazah-backend-app-1:8000'

export async function actionFetch<T>(
  url: string,
  options?: RequestInit,
  businessMessages?: BusinessErrorMessages,
): Promise<T | null> {
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
    if (businessMessages) await requireActionResponse(response, businessMessages)
    const errorBody = await response.text().catch(() => '')
    let errorMessage = `请求失败: ${response.status} ${response.statusText}`
    try {
      const errorJson = JSON.parse(errorBody)
      if (errorJson.detail) errorMessage = typeof errorJson.detail === 'string' ? errorJson.detail : JSON.stringify(errorJson.detail)
      else if (errorJson.message) errorMessage = errorJson.message
    } catch {}
    throw new ActionRequestError(response.status, response.status >= 500 ? '服务暂时不可用，请稍后重试' : errorMessage)
  }
  if (response.status === 204) return null
  const result = await response.json()
  return result.data
}
