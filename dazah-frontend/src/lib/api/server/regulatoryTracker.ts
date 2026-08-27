import { cookies } from 'next/headers'

const API_BASE_URL =
  process.env.API_BASE_URL ||
  process.env.INTERNAL_API_BASE_URL ||
  'http://dazah-backend-app-1:8000'

interface ApiEnvelope<T> {
  code: number
  message: string
  data: T
}

export interface RegulatoryTrackerSummaryStats {
  totalCount: number
  todayNewCount: number
  unreadNewCount: number
  lastSyncTime: string | null
  lastSyncStatus: string | null
}

export interface RegulatoryTrackerSyncJob {
  id: string
  sourceId: string
  channelId: string
  jobType: string
  startedAt: string | null
  finishedAt: string | null
  status: string
  totalPages: number | null
  checkedCount: number
  newCount: number
  updatedCount: number
  errorMessage: string | null
  createdAt: string
}

export interface RegulatoryTrackerPagedResult<T> {
  items: T[]
  total: number
  page: number
  pageSize: number
  totalPages: number
}

export interface RegulatoryTrackerListParams {
  keyword?: string
  sourceSite?: string
  publishDateFrom?: string
  publishDateTo?: string
  captureDateFrom?: string
  captureDateTo?: string
  statusText?: string
  classification?: string
  isNew?: boolean
  page?: number
  pageSize?: number
}

export interface RegulatoryTrackerListItem {
  id: string
  capture_date?: string | null
  title: string
  version_text?: string | null
  publish_date?: string | null
  effective_date?: string | null
  summary_text?: string | null
  source_url?: string | null
  source_site_name?: string | null
  is_new: boolean
  ai_summary?: string | null
  ai_analysis_status?: string | null
  ai_analyzed_at?: string | null
}

export interface RegulatoryTrackerDetail extends RegulatoryTrackerListItem {
  ai_summary?: string | null
  ai_key_points?: string[] | null
  ai_relevance_score?: number | null
  ai_analysis_status?: string | null
  ai_analyzed_at?: string | null
}

export interface RegulatoryTrackerNotificationRecipientOption {
  open_id: string
  name: string
  department?: string | null
  enterprise_email?: string | null
}

export interface RegulatoryTrackerNotificationSetting {
  is_enabled: boolean
  recent_days: number
  recipient_open_id?: string | null
  recipient_name?: string | null
  recipient_department?: string | null
  schedule_time: string
  pending_count: number
}

interface TrackerLedgerPageRead {
  items: RegulatoryTrackerListItem[]
  total: number
  page: number
  pageSize: number
  totalPages: number
}

async function parseApiResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const errorText = await response.text().catch(() => '')
    throw new Error(errorText || `请求失败: ${response.status} ${response.statusText}`)
  }

  const json = (await response.json()) as ApiEnvelope<T>
  return json.data
}

function buildListSearchParams(params: RegulatoryTrackerListParams = {}): URLSearchParams {
  const searchParams = new URLSearchParams()

  if (params.keyword) searchParams.set('keyword', params.keyword)
  if (params.sourceSite) searchParams.set('sourceSite', params.sourceSite)
  if (params.publishDateFrom) searchParams.set('publishDateFrom', params.publishDateFrom)
  if (params.publishDateTo) searchParams.set('publishDateTo', params.publishDateTo)
  if (params.captureDateFrom) searchParams.set('captureDateFrom', params.captureDateFrom)
  if (params.captureDateTo) searchParams.set('captureDateTo', params.captureDateTo)
  if (params.statusText) searchParams.set('statusText', params.statusText)
  if (params.classification) searchParams.set('classification', params.classification)
  if (params.isNew !== undefined && params.isNew !== null) {
    searchParams.set('isNew', String(params.isNew))
  }
  if (params.page) searchParams.set('page', String(params.page))
  if (params.pageSize) searchParams.set('pageSize', String(params.pageSize))

  return searchParams
}

async function serverFetch<T>(path: string): Promise<T> {
  const cookieStore = await cookies()
  const authToken = cookieStore.get('auth_token')?.value
  const response = await fetch(`${API_BASE_URL}${path}`, {
    cache: 'no-store',
    headers: authToken ? { Authorization: `Bearer ${authToken}` } : undefined,
  })

  return parseApiResponse<T>(response)
}

export async function fetchRegulatoryTrackerSummaryServer(): Promise<RegulatoryTrackerSummaryStats> {
  return serverFetch<RegulatoryTrackerSummaryStats>('/api/v1/regulatory-tracker/summary')
}

export async function fetchRegulatoryTrackerDocumentsServer(
  params: RegulatoryTrackerListParams = {}
): Promise<RegulatoryTrackerPagedResult<RegulatoryTrackerListItem>> {
  const searchParams = buildListSearchParams(params)
  const suffix = searchParams.size ? `?${searchParams.toString()}` : ''
  const pageData = await serverFetch<TrackerLedgerPageRead>(`/api/v1/regulatory-documents${suffix}`)

  return {
    items: pageData.items,
    total: pageData.total,
    page: pageData.page,
    pageSize: pageData.pageSize,
    totalPages: pageData.totalPages,
  }
}

export async function fetchRegulatoryTrackerDocumentDetailServer(
  docId: string
): Promise<RegulatoryTrackerDetail | null> {
  return serverFetch<RegulatoryTrackerDetail | null>(
    `/api/v1/regulatory-documents/${encodeURIComponent(docId)}`
  )
}

export async function fetchRegulatoryTrackerSyncJobsServer(
  page: number = 1,
  pageSize: number = 20
): Promise<RegulatoryTrackerPagedResult<RegulatoryTrackerSyncJob>> {
  const searchParams = new URLSearchParams({
    page: String(page),
    pageSize: String(pageSize),
  })

  return serverFetch<RegulatoryTrackerPagedResult<RegulatoryTrackerSyncJob>>(
    `/api/v1/sync-jobs?${searchParams.toString()}`
  )
}

export async function fetchRegulatoryTrackerNotificationSettingsServer(): Promise<RegulatoryTrackerNotificationSetting> {
  return serverFetch<RegulatoryTrackerNotificationSetting>(
    '/api/v1/regulatory-documents/notification-settings'
  )
}

export async function fetchRegulatoryTrackerNotificationRecipientsServer(): Promise<
  RegulatoryTrackerNotificationRecipientOption[]
> {
  return serverFetch<RegulatoryTrackerNotificationRecipientOption[]>(
    '/api/v1/regulatory-documents/notification-recipients'
  )
}
