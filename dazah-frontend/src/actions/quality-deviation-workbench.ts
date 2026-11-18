'use server'

import { revalidatePath } from 'next/cache'
import { serverActionResult, type BusinessErrorMessages } from '@/lib/server-action-result'
import { uncertainWriteMessage } from '@/lib/user-error'
import type { components } from '@/types/generated/schema'
import type {
  CreateDeviationWorkbenchPayload,
  CreateHistoricalDeviationPayload,
  DeviationWorkbenchAttachmentDescriptor,
  DeviationWorkbenchReportDetail,
  DeviationWorkbenchSettings,
  HistoricalDeviationBatchImportResult,
  HistoricalDeviationDetail,
} from '@/types/quality'
import { API_BASE_URL, actionFetch } from './quality-shared'

function revalidateDeviationWorkbenchPaths() {
  revalidatePath('/quality')
  revalidatePath('/quality/deviations')
  revalidatePath('/quality/deviations/history')
  revalidatePath('/quality/deviations/workbench')
}

function uploadDeviationFile<T>(
  operation: string,
  label: string,
  path: string,
  formData: FormData,
  businessMessages: BusinessErrorMessages = {},
) {
  return serverActionResult(`quality.deviation.${operation}`, async () => {
    const result = await actionFetch<T>(
      `${API_BASE_URL}/api/v1/quality${path}`,
      { method: 'POST', body: formData },
      businessMessages,
    )
    if (result == null) throw new Error('Missing upload result')
    revalidateDeviationWorkbenchPaths()
    return result
  }, uncertainWriteMessage(label))
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
) {
  return uploadDeviationFile<{ id: string; file_name: string; url: string; converted: boolean }>(
    'history.uploadAttachment', '历史偏差附件上传', `/historical-deviations/${encodeURIComponent(recordId)}/attachments`, formData,
  )
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
) {
  return uploadDeviationFile<DeviationWorkbenchAttachmentDescriptor>(
    'workbench.uploadAttachment', '偏差工作台附件上传', '/deviation-workbench/attachments', formData,
  )
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

/** 批量导入历史偏差附件：转 MD + 建记录 + 解析编号 + AI 提取 */
export async function batchImportHistoricalDeviations(
  formData: FormData
) {
  const batchMessages = {
    QUALITY_HISTORICAL_DEVIATION_BATCH_LIMIT: '本次附件数量过多，请分批导入',
  } satisfies Record<components['schemas']['HistoricalDeviationBatchErrorDetail']['error_code'], string>
  return uploadDeviationFile<HistoricalDeviationBatchImportResult>(
    'history.batchImport', '历史偏差批量导入', '/historical-deviations/batch-import', formData, { 400: batchMessages },
  )
}
