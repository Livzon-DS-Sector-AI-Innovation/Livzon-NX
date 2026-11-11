/**
 * 行政管理模块的服务端读取封装（Server Component 预取）。
 *
 * 只做请求、认证与错误标准化；业务组件按需传入页面上下文头。
 */

import { getAuthHeaders } from '@/lib/auth'
import { serverApiUrl } from '@/lib/server-api'
import type { TobaccoGiftDashboardStats } from '@/types/administration'

interface ApiEnvelope<T> {
  code?: number
  message?: string
  detail?: string | { message?: string }
  data: T
}

const REQUEST_TIMEOUT_MS = 8000

export async function fetchTobaccoGiftDashboardStats(
  pageKey: string,
): Promise<TobaccoGiftDashboardStats> {
  const authHeaders = await getAuthHeaders()
  const response = await fetch(serverApiUrl('/administration/tobacco-gift/dashboard-stats'), {
    headers: { ...authHeaders, 'X-Dazah-Page-Key': pageKey },
    cache: 'no-store',
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  })
  const body = (await response.json().catch(() => null)) as ApiEnvelope<TobaccoGiftDashboardStats> | null
  if (!response.ok || !body) {
    const detail = typeof body?.detail === 'string' ? body.detail : body?.detail?.message
    throw new Error(detail || body?.message || `读取烟酒礼品统计失败（${response.status}）`)
  }
  return body.data
}
