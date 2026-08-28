'use client'

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

export interface RegulatoryTrackerNotificationSettingInput {
  is_enabled: boolean
  recent_days: number
  recipient_open_id?: string | null
}

export interface RegulatoryTrackerAnalyzeSingleResult {
  id: string
  analyzed: boolean
}

export interface RegulatoryTrackerAnalyzeBatchResult {
  analyzed: number
  failed: number
  skipped: number
}

export interface RegulatoryTrackerManualSyncTotals {
  checked: number
  accepted: number
  inserted: number
  updated: number
  unchanged: number
  rejected: number
}

export interface RegulatoryTrackerManualSyncAnalysis {
  analyzed: number
  failed: number
  skipped: number
}

export interface RegulatoryTrackerManualSyncSiteResult {
  site_code: string
  site_name: string
  totals: RegulatoryTrackerManualSyncTotals
  rejection_reasons: Record<string, number>
  error?: string | null
}

export interface RegulatoryTrackerManualSyncBootstrap {
  created_sources: number
  created_channels: number
  site_count: number
  sites: string[]
}

export interface RegulatoryTrackerManualSyncResult {
  bootstrap: RegulatoryTrackerManualSyncBootstrap
  totals: RegulatoryTrackerManualSyncTotals
  sites: RegulatoryTrackerManualSyncSiteResult[]
  analysis: RegulatoryTrackerManualSyncAnalysis
}

export interface RegulatoryTrackerSyncStarted {
  status: 'started'
  message: string
}

export type RegulatoryTrackerSyncStatus = 'idle' | 'running' | 'completed' | 'failed'

export interface RegulatoryTrackerSyncState {
  status: RegulatoryTrackerSyncStatus
  started_at: number | null
  completed_at: number | null
  result: RegulatoryTrackerManualSyncResult | null
  error: string | null
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

export async function fetchRegulatoryTrackerSummaryClient(): Promise<RegulatoryTrackerSummaryStats> {
  const response = await fetch('/api/v1/regulatory-tracker/summary', {
    cache: 'no-store',
  })

  return parseApiResponse<RegulatoryTrackerSummaryStats>(response)
}

export async function fetchRegulatoryTrackerDocumentsClient(
  params: RegulatoryTrackerListParams = {}
): Promise<RegulatoryTrackerPagedResult<RegulatoryTrackerListItem>> {
  const searchParams = buildListSearchParams(params)
  const suffix = searchParams.size ? `?${searchParams.toString()}` : ''
  const response = await fetch(`/api/v1/regulatory-documents${suffix}`, {
    cache: 'no-store',
  })
  const pageData = await parseApiResponse<TrackerLedgerPageRead>(response)

  return {
    items: pageData.items,
    total: pageData.total,
    page: pageData.page,
    pageSize: pageData.pageSize,
    totalPages: pageData.totalPages,
  }
}

export async function fetchRegulatoryTrackerDocumentDetailClient(
  docId: string
): Promise<RegulatoryTrackerDetail | null> {
  const response = await fetch(`/api/v1/regulatory-documents/${encodeURIComponent(docId)}`, {
    cache: 'no-store',
  })

  return parseApiResponse<RegulatoryTrackerDetail | null>(response)
}

export async function fetchRegulatoryTrackerSyncJobsClient(
  page: number = 1,
  pageSize: number = 20
): Promise<RegulatoryTrackerPagedResult<RegulatoryTrackerSyncJob>> {
  const searchParams = new URLSearchParams({
    page: String(page),
    pageSize: String(pageSize),
  })
  const response = await fetch(`/api/v1/sync-jobs?${searchParams.toString()}`, {
    cache: 'no-store',
  })

  return parseApiResponse<RegulatoryTrackerPagedResult<RegulatoryTrackerSyncJob>>(response)
}

export async function analyzeRegulatoryDocumentClient(
  docId: string
): Promise<RegulatoryTrackerAnalyzeSingleResult | null> {
  const response = await fetch(`/api/v1/regulatory-documents/${encodeURIComponent(docId)}/analyze`, {
    method: 'POST',
  })

  return parseApiResponse<RegulatoryTrackerAnalyzeSingleResult | null>(response)
}

export async function analyzeRegulatoryDocumentsClient(
  limit: number = 10
): Promise<RegulatoryTrackerAnalyzeBatchResult | null> {
  const searchParams = new URLSearchParams({
    limit: String(limit),
  })
  const response = await fetch(`/api/v1/regulatory-documents/analyze?${searchParams.toString()}`, {
    method: 'POST',
  })

  return parseApiResponse<RegulatoryTrackerAnalyzeBatchResult | null>(response)
}

export async function manualSyncRegulatoryTrackerClient(
  recentDays: number
): Promise<RegulatoryTrackerSyncStarted | null> {
  const response = await fetch(`/api/v1/regulatory-documents/sync?recentDays=${recentDays}`, {
    method: 'POST',
  })

  return parseApiResponse<RegulatoryTrackerSyncStarted | null>(response)
}

export async function fetchRegulatoryTrackerSyncStatusClient(): Promise<RegulatoryTrackerSyncState | null> {
  const response = await fetch('/api/v1/regulatory-documents/sync/status', {
    cache: 'no-store',
  })

  return parseApiResponse<RegulatoryTrackerSyncState | null>(response)
}

export async function fetchRegulatoryTrackerNotificationSettingsClient(): Promise<RegulatoryTrackerNotificationSetting> {
  const response = await fetch('/api/v1/regulatory-documents/notification-settings', {
    cache: 'no-store',
  })

  return parseApiResponse<RegulatoryTrackerNotificationSetting>(response)
}

export async function fetchRegulatoryTrackerNotificationRecipientsClient(): Promise<
  RegulatoryTrackerNotificationRecipientOption[]
> {
  const response = await fetch('/api/v1/regulatory-documents/notification-recipients', {
    cache: 'no-store',
  })

  return parseApiResponse<RegulatoryTrackerNotificationRecipientOption[]>(response)
}

export async function updateRegulatoryTrackerNotificationSettingsClient(
  data: RegulatoryTrackerNotificationSettingInput
): Promise<RegulatoryTrackerNotificationSetting | null> {
  const response = await fetch('/api/v1/regulatory-documents/notification-settings', {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  })

  return parseApiResponse<RegulatoryTrackerNotificationSetting | null>(response)
}
