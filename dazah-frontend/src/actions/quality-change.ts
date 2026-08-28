'use server'

import { revalidatePath } from 'next/cache'
import {
  QualityAiAnalysisLog,
} from '@/types/quality'
import type { CreateChangeRequest, UpdateChangeRequest } from '@/types/quality'
import { API_BASE_URL, actionFetch } from './quality-shared'

function revalidateChangePaths() {
  revalidatePath('/quality')
  revalidatePath('/quality/change')
  revalidatePath('/quality/change/ledger')
  revalidatePath('/quality/file-change/ledger')
  revalidatePath('/quality/change/action-plans')
}

export async function createChange(data: CreateChangeRequest) {
  const result = await actionFetch(
    `${API_BASE_URL}/api/v1/quality/changes`,
    {
      method: 'POST',
      body: JSON.stringify(data),
    }
  )
  revalidateChangePaths()
  return result
}

export async function updateChange(changeId: string, data: UpdateChangeRequest) {
  const result = await actionFetch(
    `${API_BASE_URL}/api/v1/quality/changes/${changeId}`,
    {
      method: 'PUT',
      body: JSON.stringify(data),
    }
  )
  revalidateChangePaths()
  return result
}

export async function deleteChange(changeId: string) {
  await actionFetch(
    `${API_BASE_URL}/api/v1/quality/changes/${changeId}`,
    { method: 'DELETE' }
  )
  revalidateChangePaths()
}

export async function batchDeleteChanges(ids: string[]) {
  const result = await actionFetch<{ deleted: number; failed: string[] }>(
    `${API_BASE_URL}/api/v1/quality/changes/batch-delete`,
    {
      method: 'POST',
      body: JSON.stringify({ ids }),
    }
  )
  revalidateChangePaths()
  return result ?? { deleted: 0, failed: [] }
}

// ============ Change Action Plan Actions ============

function revalidateChangeActionPlanPaths(changeId?: string) {
  revalidatePath('/quality')
  revalidatePath('/quality/change')
  revalidatePath('/quality/change/action-plans')
  if (changeId) {
    revalidatePath(`/quality/change/${changeId}`)
  }
}

export async function createChangeActionPlan(data: Record<string, unknown>) {
  const result = await actionFetch(
    `${API_BASE_URL}/api/v1/quality/change-action-plans`,
    {
      method: 'POST',
      body: JSON.stringify(data),
    }
  )
  revalidateChangeActionPlanPaths(data.change_id as string | undefined)
  return result
}

export async function updateChangeActionPlan(id: string, data: Record<string, unknown>) {
  const result = await actionFetch(
    `${API_BASE_URL}/api/v1/quality/change-action-plans/${id}`,
    {
      method: 'PUT',
      body: JSON.stringify(data),
    }
  )
  revalidateChangeActionPlanPaths(data.change_id as string | undefined)
  return result
}

export async function deleteChangeActionPlan(id: string) {
  await actionFetch(
    `${API_BASE_URL}/api/v1/quality/change-action-plans/${id}`,
    { method: 'DELETE' }
  )
  revalidateChangeActionPlanPaths()
}

export async function syncChangeActionPlansFromFeishu() {
  const result = await actionFetch<{ synced: number; failed: number }>(
    `${API_BASE_URL}/api/v1/quality/change-action-plans/sync-from-feishu`,
    { method: 'POST' }
  )
  revalidateChangeActionPlanPaths()
  return result ?? { synced: 0, failed: 0 }
}

export async function syncChangeActionPlanToFeishu(planId: string) {
  const result = await actionFetch(
    `${API_BASE_URL}/api/v1/quality/change-action-plans/${planId}/sync-to-feishu`,
    { method: 'POST' }
  )
  revalidateChangeActionPlanPaths()
  return result
}

// ============ AI Analysis Actions ============

export async function analyzeChangeAi(changeId: string): Promise<QualityAiAnalysisLog | null> {
  const result = await actionFetch<QualityAiAnalysisLog>(
    `${API_BASE_URL}/api/v1/quality/ai/changes/${changeId}/analyze`,
    { method: 'POST' }
  )
  revalidatePath('/quality/change')
  return result
}

export async function previewChangeImport(formData: FormData, changeType: string = 'technical') {
  const result = await actionFetch<any>(
    `${API_BASE_URL}/api/v1/quality/changes/import/preview?change_type=${changeType}`,
    {
      method: 'POST',
      body: formData,
    }
  )
  revalidatePath('/quality/change')
  return result
}

export async function confirmChangeImport(formData: FormData, skipDuplicates: boolean, updateExisting: boolean, changeType: string = 'technical') {
  const result = await actionFetch<any>(
    `${API_BASE_URL}/api/v1/quality/changes/import/confirm?skip_duplicates=${skipDuplicates}&update_existing=${updateExisting}&change_type=${changeType}`,
    {
      method: 'POST',
      body: formData,
    }
  )
  revalidatePath('/quality')
  revalidatePath('/quality/change')
  return result
}
