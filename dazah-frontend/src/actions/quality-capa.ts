'use server'

import { revalidatePath } from 'next/cache'
import {
  CreateCapaPlanTrackRequest,
  CreateCapaRequest,
  UpdateCapaPlanTrackRequest,
  QualityAiAnalysisLog,
} from '@/types/quality'
import { API_BASE_URL, actionFetch } from './quality-shared'

export async function createCapa(data: CreateCapaRequest) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/quality/capas`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/quality')
  revalidatePath('/quality/capas')
  return result
}

export async function updateCapa(capaId: string, data: Record<string, unknown>) {
  const result = await actionFetch<{ success: boolean }>(`${API_BASE_URL}/api/v1/quality/capas/${capaId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath('/quality')
  revalidatePath('/quality/capas')
  revalidatePath(`/quality/capas/${capaId}`)
  return result
}

export async function deleteCapa(capaId: string) {
  await actionFetch(`${API_BASE_URL}/api/v1/quality/capas/${capaId}`, {
    method: 'DELETE',
  })
  revalidatePath('/quality')
  revalidatePath('/quality/capas')
}

export async function batchDeleteCapas(ids: string[]): Promise<{ deleted: number; failed: string[] }> {
  const result = await actionFetch<{ deleted?: number; failed_ids?: string[] }>(
    `${API_BASE_URL}/api/v1/quality/capas/batch-delete`,
    {
      method: 'POST',
      body: JSON.stringify({ ids }),
    }
  )
  revalidatePath('/quality')
  revalidatePath('/quality/capas')
  return { deleted: result?.deleted ?? 0, failed: result?.failed_ids ?? [] }
}

export async function submitCapa(capaId: string) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/quality/capas/${capaId}/submit`, {
    method: 'POST',
  })
  revalidatePath('/quality')
  revalidatePath('/quality/capas')
  revalidatePath(`/quality/capas/${capaId}`)
  return result
}

export async function approveCapa(capaId: string, data: Record<string, unknown>) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/quality/capas/${capaId}/approve`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/quality')
  revalidatePath('/quality/capas')
  revalidatePath(`/quality/capas/${capaId}`)
  return result
}

export async function resubmitCapa(capaId: string) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/quality/capas/${capaId}/resubmit`, {
    method: 'POST',
  })
  revalidatePath('/quality')
  revalidatePath('/quality/capas')
  revalidatePath(`/quality/capas/${capaId}`)
  return result
}

export async function addExecutionTrack(capaId: string, data: Record<string, unknown>) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/quality/capas/${capaId}/add-execution-track`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/quality')
  revalidatePath('/quality/capas')
  revalidatePath(`/quality/capas/${capaId}`)
  return result
}

export async function deleteExecutionTrack(capaId: string, index: number) {
  await actionFetch(`${API_BASE_URL}/api/v1/quality/capas/${capaId}/delete-execution-track?index=${encodeURIComponent(index)}`, {
    method: 'POST',
  })
  revalidatePath('/quality')
  revalidatePath('/quality/capas')
  revalidatePath(`/quality/capas/${capaId}`)
}

export async function confirmExecution(capaId: string, data: Record<string, unknown> = {}) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/quality/capas/${capaId}/confirm-execution`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/quality')
  revalidatePath('/quality/capas')
  revalidatePath(`/quality/capas/${capaId}`)
  return result
}

export async function submitEvaluation(capaId: string, data: Record<string, unknown>) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/quality/capas/${capaId}/submit-evaluation`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/quality')
  revalidatePath('/quality/capas')
  revalidatePath(`/quality/capas/${capaId}`)
  return result
}

export async function completeCapaPart(capaId: string, part: string) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/quality/capas/${capaId}/complete-part`, {
    method: 'POST',
    body: JSON.stringify({ part }),
  })
  revalidatePath('/quality')
  revalidatePath('/quality/capas')
  revalidatePath(`/quality/capas/${capaId}`)
  return result
}

export async function confirmDeptHead(capaId: string, data: Record<string, unknown>) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/quality/capas/${capaId}/confirm-dept-head`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/quality')
  revalidatePath('/quality/capas')
  revalidatePath(`/quality/capas/${capaId}`)
  return result
}

export async function createCapaPlanTrack(data: CreateCapaPlanTrackRequest) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/quality/capa-plan-tracks`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/quality')
  revalidatePath('/quality/capas')
  revalidatePath('/quality/capas/plans')
  return result
}

export async function deleteCapaPlanTrack(trackId: string): Promise<void> {
  await actionFetch(`${API_BASE_URL}/api/v1/quality/capa-plan-tracks/${trackId}`, {
    method: 'DELETE',
  })
  revalidatePath('/quality')
  revalidatePath('/quality/capas')
  revalidatePath('/quality/capas/plans')
}

export async function syncCapaPlanTracksFromFeishu() {
  const result = await actionFetch<{ synced: number; failed: number }>(
    `${API_BASE_URL}/api/v1/quality/capa-plan-tracks/sync-from-feishu`,
    { method: 'POST' }
  )
  revalidatePath('/quality')
  revalidatePath('/quality/capas')
  revalidatePath('/quality/capas/plans')
  return result ?? { synced: 0, failed: 0 }
}

export async function updateCapaPlanTrack(
  trackId: string,
  data: UpdateCapaPlanTrackRequest
) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/quality/capa-plan-tracks/${trackId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath('/quality')
  revalidatePath('/quality/capas')
  revalidatePath('/quality/capas/plans')
  return result
}

export async function syncCapaPlanTrackToFeishu(trackId: string) {
  const result = await actionFetch<{ record_id?: string; table_id?: string }>(
    `${API_BASE_URL}/api/v1/quality/feishu-sync/capa-plan-tracks/${trackId}`,
    {
      method: 'POST',
    }
  )
  revalidatePath('/quality')
  revalidatePath('/quality/capas')
  revalidatePath('/quality/capas/plans')
  return result
}

// ============ Feishu Native CAPA Plan Track Actions ============

export async function createFeishuCapaPlanTrack(data: Record<string, unknown>): Promise<{ record_id: string }> {
  const result = await actionFetch<{ record_id: string }>(
    `${API_BASE_URL}/api/v1/quality/feishu/capa-plan-tracks`,
    {
      method: 'POST',
      body: JSON.stringify(data),
    }
  )
  revalidatePath('/quality')
  revalidatePath('/quality/capas')
  revalidatePath('/quality/capas/plans')
  return result ?? { record_id: '' }
}

export async function updateFeishuCapaPlanTrack(recordId: string, data: Record<string, unknown>): Promise<void> {
  await actionFetch(`${API_BASE_URL}/api/v1/quality/feishu/capa-plan-tracks/${recordId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath('/quality')
  revalidatePath('/quality/capas')
  revalidatePath('/quality/capas/plans')
}

export async function deleteFeishuCapaPlanTrack(recordId: string): Promise<void> {
  await actionFetch(`${API_BASE_URL}/api/v1/quality/feishu/capa-plan-tracks/${recordId}`, {
    method: 'DELETE',
  })
  revalidatePath('/quality')
  revalidatePath('/quality/capas')
  revalidatePath('/quality/capas/plans')
}

export async function analyzeCapaAi(capaId: string): Promise<QualityAiAnalysisLog | null> {
  const result = await actionFetch<QualityAiAnalysisLog>(
    `${API_BASE_URL}/api/v1/quality/ai/capas/${capaId}/analyze`,
    { method: 'POST' }
  )
  revalidatePath('/quality/capas')
  return result
}

export async function previewCapaImport(formData: FormData) {
  const result = await actionFetch<any>(
    `${API_BASE_URL}/api/v1/quality/capas/import/preview`,
    {
      method: 'POST',
      body: formData,
    }
  )
  revalidatePath('/quality/capas')
  return result
}

export async function confirmCapaImport(formData: FormData, skipDuplicates: boolean, updateExisting: boolean) {
  const result = await actionFetch<any>(
    `${API_BASE_URL}/api/v1/quality/capas/import/confirm?skip_duplicates=${skipDuplicates}&update_existing=${updateExisting}`,
    {
      method: 'POST',
      body: formData,
    }
  )
  revalidatePath('/quality')
  revalidatePath('/quality/capas')
  return result
}
