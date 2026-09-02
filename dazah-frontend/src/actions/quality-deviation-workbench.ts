'use server'

import { revalidatePath } from 'next/cache'
import type {
  CreateDeviationWorkbenchPayload,
  CreateHistoricalDeviationPayload,
  DeviationWorkbenchAttachmentDescriptor,
  DeviationWorkbenchReportDetail,
  DeviationWorkbenchSettings,
  HistoricalDeviationDetail,
} from '@/types/quality'
import { API_BASE_URL, actionFetch } from './quality-shared'

function revalidateDeviationWorkbenchPaths() {
  revalidatePath('/quality')
  revalidatePath('/quality/deviations')
  revalidatePath('/quality/deviations/history')
  revalidatePath('/quality/deviations/workbench')
}

// ============ 历史偏差 ============

export async function createHistoricalDeviation(
  data: CreateHistoricalDeviationPayload
): Promise<HistoricalDeviationDetail | null> {
  const result = await actionFetch<HistoricalDeviationDetail>(
    `${API_BASE_URL}/api/v1/quality/historical-deviations`,
    { method: 'POST', body: JSON.stringify(data) }
  )
  revalidateDeviationWorkbenchPaths()
  return result
}

export async function updateHistoricalDeviation(
  recordId: string,
  data: CreateHistoricalDeviationPayload
): Promise<HistoricalDeviationDetail | null> {
  const result = await actionFetch<HistoricalDeviationDetail>(
    `${API_BASE_URL}/api/v1/quality/historical-deviations/${recordId}`,
    { method: 'PUT', body: JSON.stringify(data) }
  )
  revalidateDeviationWorkbenchPaths()
  return result
}

export async function deleteHistoricalDeviation(recordId: string): Promise<void> {
  await actionFetch(`${API_BASE_URL}/api/v1/quality/historical-deviations/${recordId}`, {
    method: 'DELETE',
  })
  revalidateDeviationWorkbenchPaths()
}

export async function uploadHistoricalDeviationAttachment(
  recordId: string,
  formData: FormData
): Promise<{ id: string; file_name: string; url: string; converted: boolean } | null> {
  const result = await actionFetch<{ id: string; file_name: string; url: string; converted: boolean }>(
    `${API_BASE_URL}/api/v1/quality/historical-deviations/${recordId}/attachments`,
    { method: 'POST', body: formData }
  )
  revalidateDeviationWorkbenchPaths()
  return result
}

export async function deleteHistoricalDeviationAttachment(
  recordId: string,
  attachmentId: string
): Promise<HistoricalDeviationDetail | null> {
  const result = await actionFetch<HistoricalDeviationDetail>(
    `${API_BASE_URL}/api/v1/quality/historical-deviations/${recordId}/attachments/${attachmentId}`,
    { method: 'DELETE' }
  )
  revalidateDeviationWorkbenchPaths()
  return result
}

export async function aiExtractHistoricalDeviation(
  recordId: string
): Promise<HistoricalDeviationDetail | null> {
  const result = await actionFetch<HistoricalDeviationDetail>(
    `${API_BASE_URL}/api/v1/quality/historical-deviations/${recordId}/ai-extract`,
    { method: 'POST' }
  )
  revalidateDeviationWorkbenchPaths()
  return result
}

// ============ 偏差工作台 ============

export async function updateDeviationWorkbenchSettings(
  reportSystemPrompt: string
): Promise<DeviationWorkbenchSettings | null> {
  const result = await actionFetch<DeviationWorkbenchSettings>(
    `${API_BASE_URL}/api/v1/quality/deviation-workbench/settings`,
    { method: 'PUT', body: JSON.stringify({ report_system_prompt: reportSystemPrompt }) }
  )
  revalidateDeviationWorkbenchPaths()
  return result
}

export async function uploadDeviationWorkbenchAttachment(
  formData: FormData
): Promise<DeviationWorkbenchAttachmentDescriptor | null> {
  const result = await actionFetch<DeviationWorkbenchAttachmentDescriptor>(
    `${API_BASE_URL}/api/v1/quality/deviation-workbench/attachments`,
    { method: 'POST', body: formData }
  )
  revalidateDeviationWorkbenchPaths()
  return result
}

export async function analyzeDeviationWorkbench(
  data: CreateDeviationWorkbenchPayload
): Promise<DeviationWorkbenchReportDetail | null> {
  const result = await actionFetch<DeviationWorkbenchReportDetail>(
    `${API_BASE_URL}/api/v1/quality/deviation-workbench/analyze`,
    { method: 'POST', body: JSON.stringify(data) }
  )
  revalidateDeviationWorkbenchPaths()
  return result
}

export async function deleteDeviationWorkbenchReport(reportId: string): Promise<void> {
  await actionFetch(`${API_BASE_URL}/api/v1/quality/deviation-workbench/reports/${reportId}`, {
    method: 'DELETE',
  })
  revalidateDeviationWorkbenchPaths()
}

/** 清理已上传但未被报告消费的工作台附件对象（防止孤儿文件残留） */
export async function deleteDeviationWorkbenchAttachment(
  keys: string[]
): Promise<void> {
  const query = keys.map((key) => `keys=${encodeURIComponent(key)}`).join('&')
  await actionFetch(
    `${API_BASE_URL}/api/v1/quality/deviation-workbench/attachments${query ? `?${query}` : ''}`,
    { method: 'DELETE' }
  )
}
