'use server'

import { revalidatePath } from 'next/cache'
import {
  DeviationAiSession,
  CreateDeviationRequest,
  CreateDeviationInvestigationPushRecordRequest,
  UpdateDeviationRequest,
  FeishuDeviationInvestigationPushRecordItem,
  FeishuDeviationReportRecordItem,
  QualityAiAnalysisLog,
} from '@/types/quality'
import { API_BASE_URL, actionFetch } from './quality-shared'

function revalidateDeviationAiPaths(deviationId: string) {
  revalidatePath('/quality')
  revalidatePath('/quality/deviations')
  revalidatePath('/quality/deviations/records')
  revalidatePath(`/quality/deviations/${deviationId}`)
}

export async function createDeviation(data: CreateDeviationRequest) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/quality/deviations`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/quality')
  revalidatePath('/quality/deviations')
  revalidatePath('/quality/deviations/records')
  return result
}

export async function updateDeviation(deviationId: string, data: UpdateDeviationRequest) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/quality/deviations/${deviationId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath('/quality')
  revalidatePath('/quality/deviations')
  revalidatePath('/quality/deviations/records')
  revalidatePath(`/quality/deviations/${deviationId}`)
  return result
}

export async function deleteDeviation(deviationId: string) {
  await actionFetch(`${API_BASE_URL}/api/v1/quality/deviations/${deviationId}`, {
    method: 'DELETE',
  })
  revalidatePath('/quality')
  revalidatePath('/quality/deviations')
}

export async function submitDeviation(deviationId: string) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/quality/deviations/${deviationId}/submit`, {
    method: 'POST',
  })
  revalidatePath('/quality')
  revalidatePath('/quality/deviations')
  return result
}

export async function submitInvestigation(deviationId: string, data: Record<string, unknown>) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/quality/deviations/${deviationId}/submit-investigation`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/quality')
  revalidatePath('/quality/deviations')
  return result
}

export async function submitReview(deviationId: string, data: Record<string, unknown>) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/quality/deviations/${deviationId}/submit-review`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/quality')
  revalidatePath('/quality/deviations')
  return result
}

export async function submitFinalCode(deviationId: string, data: Record<string, unknown>) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/quality/deviations/${deviationId}/submit-final-code`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/quality')
  revalidatePath('/quality/deviations')
  return result
}

export async function resubmitDeviation(deviationId: string) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/quality/deviations/${deviationId}/resubmit`, {
    method: 'POST',
  })
  revalidatePath('/quality')
  revalidatePath('/quality/deviations')
  return result
}

export async function batchDeleteDeviations(ids: string[]) {
  const result = await actionFetch<{ deleted?: number }>(
    `${API_BASE_URL}/api/v1/quality/deviations/batch-delete`,
    {
      method: 'POST',
      body: JSON.stringify({ ids }),
    }
  )
  revalidatePath('/quality')
  revalidatePath('/quality/deviations')
  return result
}

export async function updateDeviationAiSession(
  deviationId: string,
  supplementText: string
): Promise<DeviationAiSession | null> {
  const result = await actionFetch<DeviationAiSession>(
    `${API_BASE_URL}/api/v1/quality/ai/deviations/${deviationId}/session`,
    {
      method: 'PUT',
      body: JSON.stringify({ supplement_text: supplementText }),
    }
  )
  revalidateDeviationAiPaths(deviationId)
  return result
}

export async function regenerateDeviationAiSession(
  deviationId: string
): Promise<DeviationAiSession | null> {
  const result = await actionFetch<DeviationAiSession>(
    `${API_BASE_URL}/api/v1/quality/ai/deviations/${deviationId}/session/regenerate`,
    {
      method: 'POST',
    }
  )
  revalidateDeviationAiPaths(deviationId)
  return result
}

export async function uploadDeviationAiSessionAttachment(
  deviationId: string,
  formData: FormData
): Promise<any> {
  const result = await actionFetch<any>(
    `${API_BASE_URL}/api/v1/quality/ai/deviations/${deviationId}/session/attachments`,
    {
      method: 'POST',
      body: formData,
    }
  )
  revalidateDeviationAiPaths(deviationId)
  return result
}

export async function deleteDeviationAiSessionAttachment(
  deviationId: string,
  attachmentId: string
): Promise<DeviationAiSession | null> {
  const result = await actionFetch<DeviationAiSession>(
    `${API_BASE_URL}/api/v1/quality/ai/deviations/${deviationId}/session/attachments/${attachmentId}`,
    {
      method: 'DELETE',
    }
  )
  revalidateDeviationAiPaths(deviationId)
  return result
}

export async function applyDeviationAiSession(
  deviationId: string,
  data: { section: 'deviation_analysis' | 'capa_suggestion'; field_keys: string[] }
): Promise<DeviationAiSession | null> {
  const result = await actionFetch<DeviationAiSession>(
    `${API_BASE_URL}/api/v1/quality/ai/deviations/${deviationId}/session/apply`,
    {
      method: 'POST',
      body: JSON.stringify(data),
    }
  )
  revalidateDeviationAiPaths(deviationId)
  return result
}

// ============ CAPA Actions ============
export async function ensureDeviationFromReportRecord(recordId: string) {
  const result = await actionFetch<{ deviation_id: string; deviation_code?: string; created?: boolean }>(
    `${API_BASE_URL}/api/v1/quality/deviation-report-records/${recordId}/ensure-deviation`,
    {
      method: 'POST',
    }
  )
  revalidatePath('/quality')
  revalidatePath('/quality/deviations')
  revalidatePath('/quality/deviations/records')
  return result
}

export async function createDeviationInvestigationPushRecord(
  data: CreateDeviationInvestigationPushRecordRequest
): Promise<FeishuDeviationInvestigationPushRecordItem | null> {
  const result = await actionFetch<FeishuDeviationInvestigationPushRecordItem>(
    `${API_BASE_URL}/api/v1/quality/deviation-investigation-push-records`,
    {
      method: 'POST',
      body: JSON.stringify(data),
    }
  )
  revalidatePath('/quality')
  revalidatePath('/quality/deviations')
  revalidatePath('/quality/deviations/investigations')
  return result
}

export async function updateDeviationInvestigationPushRecord(
  recordId: string,
  data: Record<string, unknown>
): Promise<FeishuDeviationInvestigationPushRecordItem | null> {
  const result = await actionFetch<FeishuDeviationInvestigationPushRecordItem>(
    `${API_BASE_URL}/api/v1/quality/deviation-investigation-push-records/${recordId}`,
    {
      method: 'PUT',
      body: JSON.stringify(data),
    }
  )
  revalidatePath('/quality')
  revalidatePath('/quality/deviations')
  revalidatePath('/quality/deviations/investigations')
  return result
}

export async function deleteDeviationInvestigationPushRecord(recordId: string): Promise<void> {
  await actionFetch(`${API_BASE_URL}/api/v1/quality/deviation-investigation-push-records/${recordId}`, {
    method: 'DELETE',
  })
  revalidatePath('/quality')
  revalidatePath('/quality/deviations')
  revalidatePath('/quality/deviations/investigations')
}

export async function createDeviationReportRecord(data: {
  description: string
  product_batch: string
  reporter_open_id: string
}): Promise<FeishuDeviationReportRecordItem | null> {
  const result = await actionFetch<FeishuDeviationReportRecordItem>(
    `${API_BASE_URL}/api/v1/quality/deviation-report-records`,
    {
      method: 'POST',
      body: JSON.stringify(data),
    }
  )
  revalidatePath('/quality')
  revalidatePath('/quality/deviations')
  revalidatePath('/quality/deviations/records')
  return result
}

export async function updateDeviationReportRecord(
  recordId: string,
  data: Record<string, unknown>
): Promise<FeishuDeviationReportRecordItem | null> {
  const result = await actionFetch<FeishuDeviationReportRecordItem>(
    `${API_BASE_URL}/api/v1/quality/deviation-report-records/${recordId}`,
    {
      method: 'PUT',
      body: JSON.stringify(data),
    }
  )
  revalidatePath('/quality')
  revalidatePath('/quality/deviations')
  revalidatePath('/quality/deviations/records')
  return result
}

export async function deleteDeviationReportRecord(recordId: string): Promise<void> {
  await actionFetch(`${API_BASE_URL}/api/v1/quality/deviation-report-records/${recordId}`, {
    method: 'DELETE',
  })
  revalidatePath('/quality')
  revalidatePath('/quality/deviations')
  revalidatePath('/quality/deviations/records')
}

export async function analyzeDeviationAi(deviationId: string): Promise<QualityAiAnalysisLog | null> {
  const result = await actionFetch<QualityAiAnalysisLog>(
    `${API_BASE_URL}/api/v1/quality/ai/deviations/${deviationId}/analyze`,
    { method: 'POST' }
  )
  revalidatePath('/quality/deviations')
  return result
}

export async function suggestDeviationCapaAi(deviationId: string): Promise<QualityAiAnalysisLog | null> {
  const result = await actionFetch<QualityAiAnalysisLog>(
    `${API_BASE_URL}/api/v1/quality/ai/deviations/${deviationId}/suggest-capa`,
    { method: 'POST' }
  )
  revalidatePath('/quality/deviations')
  return result
}

export async function previewDeviationImport(formData: FormData) {
  const result = await actionFetch<any>(
    `${API_BASE_URL}/api/v1/quality/deviations/import/preview`,
    {
      method: 'POST',
      body: formData,
    }
  )
  revalidatePath('/quality/deviations')
  return result
}

export async function confirmDeviationImport(formData: FormData, skipDuplicates: boolean, updateExisting: boolean) {
  const result = await actionFetch<any>(
    `${API_BASE_URL}/api/v1/quality/deviations/import/confirm?skip_duplicates=${skipDuplicates}&update_existing=${updateExisting}`,
    {
      method: 'POST',
      body: formData,
    }
  )
  revalidatePath('/quality')
  revalidatePath('/quality/deviations')
  return result
}
