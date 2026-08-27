'use server'

import { cookies } from 'next/headers'
import { revalidatePath } from 'next/cache'

const API_BASE_URL =
  process.env.API_BASE_URL ||
  process.env.INTERNAL_API_BASE_URL ||
  'http://dazah-backend-app-1:8000'

interface RegulatoryTrackerAnalyzeSingleResult {
  id: string
  analyzed: boolean
}

interface RegulatoryTrackerAnalyzeBatchResult {
  analyzed: number
  failed: number
  skipped: number
}

interface RegulatoryTrackerManualSyncAnalysis {
  analyzed: number
  failed: number
  skipped: number
}

interface RegulatoryTrackerManualSyncTotals {
  checked: number
  accepted: number
  inserted: number
  updated: number
  unchanged: number
  rejected: number
}

interface RegulatoryTrackerManualSyncSiteResult {
  site_code: string
  site_name: string
  totals: RegulatoryTrackerManualSyncTotals
  rejection_reasons: Record<string, number>
  error?: string | null
}

interface RegulatoryTrackerManualSyncBootstrap {
  created_sources: number
  created_channels: number
  site_count: number
  sites: string[]
}

interface RegulatoryTrackerManualSyncResult {
  bootstrap: RegulatoryTrackerManualSyncBootstrap
  totals: RegulatoryTrackerManualSyncTotals
  sites: RegulatoryTrackerManualSyncSiteResult[]
  analysis: RegulatoryTrackerManualSyncAnalysis
}

function getDefaultRecentWindowDays(): number {
  return 7
}

async function actionFetch<T>(path: string, options?: RequestInit): Promise<T | null> {
  const cookieStore = await cookies()
  const authToken = cookieStore.get('auth_token')?.value
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
      ...(options?.body ? { 'Content-Type': 'application/json' } : {}),
      ...options?.headers,
    },
  })

  if (!response.ok) {
    const errorBody = await response.text().catch(() => '')
    throw new Error(errorBody || `请求失败: ${response.status} ${response.statusText}`)
  }

  if (response.status === 204) {
    return null
  }

  const result = await response.json()
  return (result.data ?? null) as T | null
}

function revalidateRegulatoryTrackerPaths() {
  revalidatePath('/registration/regulation')
}

/**
 * 标记法规文档为已读
 */
export async function markDocumentRead(id: string): Promise<{ id: string } | null> {
  const result = await actionFetch<{ id: string }>(
    `/api/v1/regulatory-documents/${encodeURIComponent(id)}/read`,
    {
      method: 'PATCH',
    }
  )

  revalidateRegulatoryTrackerPaths()
  return result
}

export async function analyzeRegulatoryDocument(
  id: string
): Promise<RegulatoryTrackerAnalyzeSingleResult | null> {
  const result = await actionFetch<RegulatoryTrackerAnalyzeSingleResult>(
    `/api/v1/regulatory-documents/${encodeURIComponent(id)}/analyze`,
    {
      method: 'POST',
    }
  )

  revalidateRegulatoryTrackerPaths()
  return result
}

export async function analyzeRegulatoryDocuments(
  limit: number = 10
): Promise<RegulatoryTrackerAnalyzeBatchResult | null> {
  const searchParams = new URLSearchParams({
    limit: String(limit),
  })
  const result = await actionFetch<RegulatoryTrackerAnalyzeBatchResult>(
    `/api/v1/regulatory-documents/analyze?${searchParams.toString()}`,
    {
      method: 'POST',
    }
  )

  revalidateRegulatoryTrackerPaths()
  return result
}

export async function manualSyncRegulatoryTracker(
  recentDays: number = getDefaultRecentWindowDays()
): Promise<RegulatoryTrackerManualSyncResult | null> {
  const result = await actionFetch<RegulatoryTrackerManualSyncResult>(
    `/api/v1/regulatory-documents/sync?recentDays=${recentDays}`,
    {
      method: 'POST',
    }
  )

  revalidateRegulatoryTrackerPaths()
  return result
}
