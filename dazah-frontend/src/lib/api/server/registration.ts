import { cookies } from 'next/headers'

import {
  AuthorizationFdaRecord,
  AuthorizationLedgerOverview,
  AuthorizationLedgerRecord,
  CertificateReminderRecipientOption,
  CertificateReminderSetting,
  CertificateSheetDetail,
  CertificateWorkbookOverview,
  DeclarationProgressSheetDetail,
  DeclarationProgressWorkbookOverview,
  FeeDashboard,
  FeeEntry,
  InspectionContact,
  KnowledgeArticleDetail,
  KnowledgeArticleListItem,
  KnowledgeCategory,
  KnowledgeOverview,
  ProjectLedgerSheetDetail,
  ProjectLedgerWorkbookOverview,
  ProjectOverview,
} from '@/types/registration'

const API_BASE_URL =
  process.env.API_BASE_URL || 'http://dazah-backend-app-1:8000'
const REGISTRATION_SERVER_REQUEST_TIMEOUT_MS = 15000

/** 服务端读取 auth_token cookie，供请求后端时携带 Bearer 认证头 */
async function getAuthHeadersForServer(): Promise<Record<string, string> | undefined> {
  const cookieStore = await cookies()
  const token = cookieStore.get('auth_token')?.value
  return token ? { Authorization: `Bearer ${token}` } : undefined
}

interface ApiEnvelope<T> {
  code: number
  message: string
  data: T
  meta?: {
    summary?: AuthorizationLedgerOverview
    page?: number
    page_size?: number
    total?: number
  }
}

async function serverApiFetch<T>(path: string): Promise<ApiEnvelope<T>> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), REGISTRATION_SERVER_REQUEST_TIMEOUT_MS)

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      cache: 'no-store',
      signal: controller.signal,
      headers: await getAuthHeadersForServer(),
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error(`请求超时（>${Math.floor(REGISTRATION_SERVER_REQUEST_TIMEOUT_MS / 1000)}秒）`)
    }
    throw error
  } finally {
    clearTimeout(timeoutId)
  }

  if (!response.ok) {
    const errorText = await response.text().catch(() => '')
    throw new Error(errorText || `请求失败: ${response.status} ${response.statusText}`)
  }

  return (await response.json()) as ApiEnvelope<T>
}

export async function serverApiGet<T>(path: string): Promise<ApiEnvelope<T>> {
  return serverApiFetch<T>(path)
}

// 统一的写操作响应处理：错误抛出 + 解包 envelope.data（空响应返回 null）
async function handleServerApiResponse<T>(response: Response): Promise<T | null> {
  if (!response.ok) {
    const errorText = await response.text().catch(() => '')
    throw new Error(errorText || `请求失败: ${response.status} ${response.statusText}`)
  }

  const text = await response.text()
  if (!text) return null
  const json = JSON.parse(text)
  return json.data ?? json
}

export async function serverApiPost<T>(path: string, body: unknown): Promise<T | null> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(await getAuthHeadersForServer()),
    },
    body: JSON.stringify(body),
  })

  return handleServerApiResponse<T>(response)
}

export async function serverApiPut<T>(path: string, body: unknown): Promise<T | null> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      ...(await getAuthHeadersForServer()),
    },
    body: JSON.stringify(body),
  })

  return handleServerApiResponse<T>(response)
}

export async function serverApiPatch<T>(path: string, body: unknown): Promise<T | null> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      ...(await getAuthHeadersForServer()),
    },
    body: JSON.stringify(body),
  })

  return handleServerApiResponse<T>(response)
}

export async function serverApiDelete<T>(path: string): Promise<T | null> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'DELETE',
    headers: await getAuthHeadersForServer(),
  })

  return handleServerApiResponse<T>(response)
}

export async function serverApiPostFormData<T>(path: string, formData: FormData): Promise<T | null> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: await getAuthHeadersForServer(),
    body: formData,
  })

  return handleServerApiResponse<T>(response)
}

export async function fetchAuthorizationLedgerServer(params?: {
  product_name?: string
  market_name?: string
  status?: string
  keyword?: string
}): Promise<{ records: AuthorizationLedgerRecord[]; overview: AuthorizationLedgerOverview }> {
  const searchParams = new URLSearchParams()
  if (params?.product_name) searchParams.set('product_name', params.product_name)
  if (params?.market_name) searchParams.set('market_name', params.market_name)
  if (params?.status) searchParams.set('status', params.status)
  if (params?.keyword) searchParams.set('keyword', params.keyword)

  const suffix = searchParams.size ? `?${searchParams.toString()}` : ''
  const result = await serverApiFetch<AuthorizationLedgerRecord[]>(
    `/api/v1/registration/authorization-letters/ledger${suffix}`
  )

  return {
    records: result.data,
    overview: result.meta?.summary || {
      total_main_records: 0,
      total_update_records: 0,
      total_products: 0,
      total_markets: 0,
      submitted_main_records: 0,
      pending_main_records: 0,
    },
  }
}

export async function fetchAuthorizationFdaServer(params?: {
  product_name?: string
  keyword?: string
}): Promise<AuthorizationFdaRecord[]> {
  const searchParams = new URLSearchParams()
  if (params?.product_name) searchParams.set('product_name', params.product_name)
  if (params?.keyword) searchParams.set('keyword', params.keyword)

  const suffix = searchParams.size ? `?${searchParams.toString()}` : ''
  const result = await serverApiFetch<AuthorizationFdaRecord[]>(
    `/api/v1/registration/authorization-letters/fda${suffix}`
  )

  return result.data
}

export async function fetchCertificateWorkbookOverviewServer(): Promise<CertificateWorkbookOverview> {
  const result = await serverApiFetch<CertificateWorkbookOverview>(
    '/api/v1/registration/certificate-management/overview'
  )

  const data = result.data && typeof result.data === 'object' && !Array.isArray(result.data)
    ? result.data as Partial<CertificateWorkbookOverview>
    : {}
  return {
    workbook_name: data.workbook_name || '药政证书台账',
    updated_at: data.updated_at || null,
    total_records: data.total_records || 0,
    sheet_count: data.sheet_count || 0,
    issuer_count: data.issuer_count || 0,
    product_count: data.product_count || 0,
    expired_count: data.expired_count || 0,
    due_90_count: data.due_90_count || 0,
    total_pages: data.total_pages || 0,
    sheet_summaries: Array.isArray(data.sheet_summaries) ? data.sheet_summaries : [],
    upcoming_expirations: Array.isArray(data.upcoming_expirations) ? data.upcoming_expirations : [],
    recent_issued: Array.isArray(data.recent_issued) ? data.recent_issued : [],
  }
}

export async function fetchCertificateReminderSettingsServer(): Promise<CertificateReminderSetting> {
  const result = await serverApiFetch<CertificateReminderSetting>(
    '/api/v1/registration/certificate-management/reminder-settings'
  )

  const data = result.data && typeof result.data === 'object' && !Array.isArray(result.data)
    ? result.data as Partial<CertificateReminderSetting>
    : {}
  return {
    is_enabled: data.is_enabled ?? false,
    reminder_days: data.reminder_days || 90,
    recipient_open_id: data.recipient_open_id || null,
    recipient_name: data.recipient_name || null,
    recipient_department: data.recipient_department || null,
    pending_count: data.pending_count || 0,
  }
}

export async function fetchCertificateReminderRecipientsServer(): Promise<
  CertificateReminderRecipientOption[]
> {
  const result = await serverApiFetch<CertificateReminderRecipientOption[]>(
    '/api/v1/registration/certificate-management/reminder-recipients'
  )

  return result.data
}

export async function fetchCertificateSheetDetailServer(
  sheetKey: string
): Promise<CertificateSheetDetail> {
  const result = await serverApiFetch<CertificateSheetDetail>(
    `/api/v1/registration/certificate-management/sheets/${encodeURIComponent(sheetKey)}`
  )

  return result.data
}

export async function fetchProjectLedgerWorkbookServer(): Promise<ProjectLedgerWorkbookOverview> {
  const result = await serverApiFetch<ProjectLedgerWorkbookOverview>(
    '/api/v1/registration/project-ledger/overview'
  )

  return result.data
}

export async function fetchProjectLedgerSheetDetailServer(
  sheetKey: string
): Promise<ProjectLedgerSheetDetail> {
  const result = await serverApiFetch<ProjectLedgerSheetDetail>(
    `/api/v1/registration/project-ledger/sheets/${encodeURIComponent(sheetKey)}`
  )

  return result.data
}

export async function fetchProjectOverviewServer(): Promise<ProjectOverview> {
  const result = await serverApiFetch<ProjectOverview>(
    '/api/v1/registration/project/overview'
  )

  return result.data
}

export async function fetchDeclarationProgressWorkbookServer(): Promise<DeclarationProgressWorkbookOverview> {
  const result = await serverApiFetch<DeclarationProgressWorkbookOverview>(
    '/api/v1/registration/declaration-progress/overview'
  )

  return result.data
}

export async function fetchDeclarationProgressSheetDetailServer(
  sheetKey: string
): Promise<DeclarationProgressSheetDetail> {
  const result = await serverApiFetch<DeclarationProgressSheetDetail>(
    `/api/v1/registration/declaration-progress/sheets/${encodeURIComponent(sheetKey)}`
  )

  return result.data
}

// ─ Fee API ────────────────────────────────────────────────────────────

export async function fetchFeeDashboardServer(yearFrom?: number): Promise<FeeDashboard> {
  const params = yearFrom ? `?year_from=${yearFrom}` : ''
  const result = await serverApiFetch<FeeDashboard>(
    `/api/v1/registration/fees/dashboard${params}`
  )
  const data = result.data && typeof result.data === 'object' && !Array.isArray(result.data)
    ? result.data as Partial<FeeDashboard>
    : {}
  return {
    total_records: data.total_records || 0,
    total_amount: data.total_amount || '0',
    pending_amount: data.pending_amount || '0',
    paid_amount: data.paid_amount || '0',
    fee_type_summaries: Array.isArray(data.fee_type_summaries) ? data.fee_type_summaries : [],
    payment_status_summaries: Array.isArray(data.payment_status_summaries) ? data.payment_status_summaries : [],
    year_summaries: Array.isArray(data.year_summaries) ? data.year_summaries : [],
    year_fee_type_summaries: Array.isArray(data.year_fee_type_summaries) ? data.year_fee_type_summaries : [],
    agency_summaries: Array.isArray(data.agency_summaries) ? data.agency_summaries : [],
    inspection_contact_count: data.inspection_contact_count || 0,
  }
}

export async function fetchFeeEntriesServer(yearFrom?: number): Promise<FeeEntry[]> {
  const params = yearFrom ? `?year_from=${yearFrom}` : ''
  const result = await serverApiFetch<FeeEntry[]>(
    `/api/v1/registration/fees/entries${params}`
  )
  return result.data
}

export async function fetchInspectionContactsServer(): Promise<InspectionContact[]> {
  const result = await serverApiFetch<InspectionContact[]>(
    '/api/v1/registration/fees/inspection-contacts'
  )
  return result.data
}

// ── Knowledge API ──────────────────────────────────────────────────────

export async function fetchKnowledgeOverviewServer(): Promise<KnowledgeOverview> {
  const result = await serverApiFetch<KnowledgeOverview>(
    '/api/v1/registration/knowledge/overview'
  )
  return result.data
}

export async function fetchKnowledgeCategoriesServer(): Promise<KnowledgeCategory[]> {
  const result = await serverApiFetch<KnowledgeCategory[]>(
    '/api/v1/registration/knowledge/categories'
  )
  return result.data
}

export async function fetchKnowledgeArticlesServer(): Promise<KnowledgeArticleListItem[]> {
  const result = await serverApiFetch<KnowledgeArticleListItem[]>(
    '/api/v1/registration/knowledge/articles'
  )
  return result.data
}

export async function fetchKnowledgeArticleDetailServer(articleId: string): Promise<KnowledgeArticleDetail> {
  const result = await serverApiFetch<KnowledgeArticleDetail>(
    `/api/v1/registration/knowledge/articles/${articleId}`
  )
  return result.data
}
