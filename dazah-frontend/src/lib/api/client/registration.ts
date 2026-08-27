import type {
  AuthorizationLedgerOverview,
  AuthorizationLedgerRecord,
  DeclarationProgressSheetDetail,
  DeclarationProgressWorkbookOverview,
  FeeDashboard,
  ProjectLedgerRecordHistory,
  ProjectLedgerSheetDetail,
  ProjectLedgerWorkbookOverview,
  ProjectOverview,
} from '@/types/registration'

const REGISTRATION_REQUEST_TIMEOUT_MS = 15000

async function fetchWithTimeout(
  url: string,
  options?: RequestInit,
  timeoutMs = REGISTRATION_REQUEST_TIMEOUT_MS
): Promise<Response> {
  const controller = new AbortController()
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs)

  try {
    return await fetch(url, {
      ...options,
      signal: controller.signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error(`请求超时（>${Math.floor(timeoutMs / 1000)}秒）`)
    }
    throw error
  } finally {
    window.clearTimeout(timeoutId)
  }
}

async function apiFetch<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetchWithTimeout(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })
  if (!response.ok) {
    throw new Error(`请求失败: ${response.status} ${response.statusText}`)
  }
  const data = await response.json()
  return data.data ?? data
}

function getDownloadFilename(response: Response, fallback: string): string {
  const contentDisposition = response.headers.get('content-disposition') || ''
  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match?.[1]) {
    return decodeURIComponent(utf8Match[1])
  }
  const plainMatch = contentDisposition.match(/filename="?([^"]+)"?/i)
  if (plainMatch?.[1]) {
    return plainMatch[1]
  }
  return fallback
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

async function throwApiError(response: Response, fallbackMessage: string): Promise<never> {
  const errorText = await response.text().catch(() => '')
  try {
    const json = JSON.parse(errorText)
    throw new Error(json.message || fallbackMessage)
  } catch {
    throw new Error(errorText || fallbackMessage)
  }
}

export async function fetchModuleInfo(): Promise<{ code: string; name: string; description: string }> {
  return apiFetch(`/api/v1/registration/`)
}

export async function fetchAuthorizationLedger(params?: {
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

  const query = searchParams.toString()
  const response = await fetchWithTimeout(
    `/api/v1/registration/authorization-letters/ledger${query ? `?${query}` : ''}`
  )
  if (!response.ok) {
    throw new Error(`请求失败: ${response.status} ${response.statusText}`)
  }

  const json = (await response.json()) as {
    data?: AuthorizationLedgerRecord[]
    meta?: {
      summary?: AuthorizationLedgerOverview
    }
  }

  return {
    records: json.data || [],
    overview: json.meta?.summary || {
      total_main_records: 0,
      total_update_records: 0,
      total_products: 0,
      total_markets: 0,
      submitted_main_records: 0,
      pending_main_records: 0,
    },
  }
}

export async function fetchAuthorizationFdaExport(params?: {
  product_name?: string
  keyword?: string
}): Promise<void> {
  const searchParams = new URLSearchParams()
  if (params?.product_name) searchParams.set('product_name', params.product_name)
  if (params?.keyword) searchParams.set('keyword', params.keyword)
  const query = searchParams.toString()
  const response = await fetchWithTimeout(
    `/api/v1/registration/authorization-letters/fda/export${query ? `?${query}` : ''}`,
    undefined,
    30000
  )
  if (!response.ok) {
    await throwApiError(response, 'FDA授权导出失败')
  }
  const blob = await response.blob()
  downloadBlob(blob, getDownloadFilename(response, 'FDA授权.docx'))
}

export async function fetchAuthorizationLedgerExport(params?: {
  product_name?: string
  market_name?: string
  status?: string
  keyword?: string
}): Promise<void> {
  const searchParams = new URLSearchParams()
  if (params?.product_name) searchParams.set('product_name', params.product_name)
  if (params?.market_name) searchParams.set('market_name', params.market_name)
  if (params?.status) searchParams.set('status', params.status)
  if (params?.keyword) searchParams.set('keyword', params.keyword)
  const query = searchParams.toString()
  const response = await fetchWithTimeout(
    `/api/v1/registration/authorization-letters/ledger/export${query ? `?${query}` : ''}`,
    undefined,
    30000
  )
  if (!response.ok) {
    await throwApiError(response, '市场授权导出失败')
  }
  const blob = await response.blob()
  downloadBlob(blob, getDownloadFilename(response, '市场授权.docx'))
}

export async function fetchCertificateWorkbookExport(): Promise<void> {
  const response = await fetchWithTimeout(
    '/api/v1/registration/certificate-management/workbook/export',
    undefined,
    30000
  )
  if (!response.ok) {
    await throwApiError(response, '药政证书台账导出失败')
  }

  const blob = await response.blob()
  downloadBlob(blob, getDownloadFilename(response, '药政证书台账-导出.xlsx'))
}

export async function fetchProjectLedgerWorkbookExport(): Promise<void> {
  const response = await fetchWithTimeout(
    '/api/v1/registration/project-ledger/workbook/export',
    undefined,
    30000
  )
  if (!response.ok) {
    await throwApiError(response, '申报台账导出失败')
  }

  const blob = await response.blob()
  downloadBlob(blob, getDownloadFilename(response, '申报台账-导出.xlsx'))
}

export async function fetchDeclarationProgressWorkbookExport(): Promise<void> {
  const response = await fetchWithTimeout(
    '/api/v1/registration/declaration-progress/workbook/export',
    undefined,
    30000
  )
  if (!response.ok) {
    await throwApiError(response, '申报进度导出失败')
  }

  const blob = await response.blob()
  downloadBlob(blob, getDownloadFilename(response, '宁夏-注册项目信息统计表.xlsx'))
}

export async function fetchDeclarationProgressRecordHistory(recordId: string) {
  const response = await fetchWithTimeout(
    `/api/v1/registration/declaration-progress/entries/${recordId}/history`
  )
  if (!response.ok) {
    await throwApiError(response, '获取申报进度历史失败')
  }
  const json = await response.json()
  return json.data
}

export async function fetchDeclarationProgressWorkbook(): Promise<DeclarationProgressWorkbookOverview> {
  return apiFetch('/api/v1/registration/declaration-progress/overview')
}

export async function fetchDeclarationProgressSheetDetail(
  sheetKey: string
): Promise<DeclarationProgressSheetDetail> {
  return apiFetch(`/api/v1/registration/declaration-progress/sheets/${encodeURIComponent(sheetKey)}`)
}

export async function fetchProjectLedgerWorkbook(): Promise<ProjectLedgerWorkbookOverview> {
  return apiFetch('/api/v1/registration/project-ledger/overview')
}

export async function fetchProjectOverview(): Promise<ProjectOverview> {
  return apiFetch('/api/v1/registration/project/overview')
}

export async function fetchProjectLedgerSheetDetail(
  sheetKey: string
): Promise<ProjectLedgerSheetDetail> {
  return apiFetch(`/api/v1/registration/project-ledger/sheets/${encodeURIComponent(sheetKey)}`)
}

export async function fetchProjectLedgerRecordHistory(
  recordId: string
): Promise<ProjectLedgerRecordHistory> {
  return apiFetch(`/api/v1/registration/project-ledger/entries/${recordId}/history`)
}

export async function fetchFeeDashboard(yearFrom: number): Promise<FeeDashboard> {
  return apiFetch(`/api/v1/registration/fees/dashboard?year_from=${yearFrom}`)
}
