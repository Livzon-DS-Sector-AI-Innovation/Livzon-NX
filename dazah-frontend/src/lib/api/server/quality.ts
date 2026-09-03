/**
 * 产品质量客户标准 - 服务器端 API
 * 使用 API_BASE_URL 环境变量（Docker 内部网络）
 */

import { cookies } from 'next/headers'

const API_BASE_URL = process.env.API_BASE_URL || 'http://dazah-backend-app-1:8000'
const QUALITY_SERVER_REQUEST_TIMEOUT_MS = 15000

/** 由 auth_token 构造 Bearer 请求头；无 token 时返回 undefined（不带鉴权） */
export function buildAuthHeaders(
  token: string | null | undefined
): Record<string, string> | undefined {
  return token ? { Authorization: `Bearer ${token}` } : undefined
}

/** 服务端读取 auth_token cookie，供请求后端时携带 Bearer 认证头 */
async function getAuthHeadersForServer(): Promise<Record<string, string> | undefined> {
  try {
    const cookieStore = await cookies()
    return buildAuthHeaders(cookieStore.get('auth_token')?.value)
  } catch {
    // 无请求上下文（构建期/测试）等价于未登录，不带鉴权头
    return undefined
  }
}

interface ApiEnvelope<T> {
  code: number
  message: string
  data: T
  meta?: {
    total?: number
    page?: number
    page_size?: number
  }
}

async function serverApiFetch<T>(path: string, options?: RequestInit): Promise<ApiEnvelope<T>> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), QUALITY_SERVER_REQUEST_TIMEOUT_MS)

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      cache: 'no-store',
      signal: controller.signal,
      ...options,
      headers: {
        ...(await getAuthHeadersForServer()),
        ...(options?.headers as Record<string, string> | undefined),
      },
    })
  } finally {
    clearTimeout(timeoutId)
  }

  if (!response.ok) {
    throw new Error(`Server API error: ${response.status} ${response.statusText}`)
  }

  return response.json()
}

export async function fetchProductQualityStandardsServer(
  productCode: string,
  params?: { keyword?: string; page?: number; page_size?: number }
) {
  const queryParts: string[] = []
  if (params) {
    if (params.keyword) queryParts.push(`keyword=${encodeURIComponent(params.keyword)}`)
    if (params.page) queryParts.push(`page=${params.page}`)
    if (params.page_size) queryParts.push(`page_size=${params.page_size}`)
  }
  const query = queryParts.length ? `?${queryParts.join('&')}` : ''
  return serverApiFetch(`/api/v1/quality/product-quality-standards/${productCode}${query}`)
}

export async function fetchProductQualityProductsServer() {
  return serverApiFetch('/api/v1/quality/product-quality-standards')
}

// ============ Server-Side API (migrated from lib/api/quality.ts) ============

const SERVER_API_BASE =
  process.env.API_BASE_URL ||
  process.env.INTERNAL_API_BASE_URL ||
  'http://dazah-backend-app-1:8000'

async function serverFetch<T>(path: string): Promise<T> {
  const url = `${SERVER_API_BASE}${path}`
  const response = await globalThis.fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      // 携带登录凭证；缺失会导致后端 401、页面被 catch 成空数据
      ...(await getAuthHeadersForServer()),
    },
    next: { revalidate: 0 },
  })
  if (!response.ok) {
    throw new Error(`请求失败: ${response.status} ${response.statusText}`)
  }
  const body = await response.json()
  return body.data ?? body
}

// ============ Page-level Server Fetch (migrated from page.tsx inline fetch) ============

export async function fetchComplaintLedgerServer(): Promise<import('@/types/quality').ComplaintLedgerItem[]> {
  try {
    return await serverFetch<import('@/types/quality').ComplaintLedgerItem[]>(
      '/api/v1/quality/complaint-ledger?page=1&page_size=200'
    )
  } catch {
    return []
  }
}

export async function fetchReturnLedgerServer(): Promise<import('@/types/quality').ReturnLedgerItem[]> {
  try {
    return await serverFetch<import('@/types/quality').ReturnLedgerItem[]>(
      '/api/v1/quality/return-ledger?page=1&page_size=200'
    )
  } catch {
    return []
  }
}

export async function fetchReturnApplicationServer(): Promise<import('@/types/quality').ReturnApplicationItem[]> {
  try {
    return await serverFetch<import('@/types/quality').ReturnApplicationItem[]>(
      '/api/v1/quality/return-application?page=1&page_size=200'
    )
  } catch {
    return []
  }
}

export async function fetchDeviationServer(id: string): Promise<any | null> {
  try {
    return await serverFetch<any>(`/api/v1/quality/deviations/${id}`)
  } catch {
    return null
  }
}

export async function fetchFeishuValidationDashboardStatsServer(): Promise<import('@/types/quality').ValidationDashboardStats> {
  return serverFetch<import('@/types/quality').ValidationDashboardStats>('/api/v1/quality/feishu/statistics/validations')
}

// ============ Document Catalog (文件管理) ============

export async function fetchDocumentDepartmentsServer(): Promise<import('@/types/quality').DocumentDepartmentItem[]> {
  try {
    return await serverFetch<import('@/types/quality').DocumentDepartmentItem[]>(
      '/api/v1/quality/document-departments'
    )
  } catch {
    return []
  }
}

// ============ Label Verification (标签复核，端点挂在 /quality 前缀下) ============

/** 标签复核记录分页列表（保留分页 meta，不使用解包版 serverFetch）。 */
export async function fetchLabelVerificationsServer(params: {
  page: number
  page_size: number
}): Promise<ApiEnvelope<import('@/types/label-verification').LabelVerification[]>> {
  const searchParams = new URLSearchParams({
    page: params.page.toString(),
    page_size: params.page_size.toString(),
  })
  return serverApiFetch<import('@/types/label-verification').LabelVerification[]>(
    `/api/v1/quality/label-verifications?${searchParams.toString()}`
  )
}
