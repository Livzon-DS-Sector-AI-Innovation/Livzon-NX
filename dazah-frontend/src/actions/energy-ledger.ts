'use server'

import { revalidatePath } from 'next/cache'
import { getAuthHeaders } from '@/lib/auth'
import {
  ledgerRequest, EnergyLedgerRequestError, type LedgerActionResult,
  type BotWrite, type Bot, type Notification, type ImportPreview, type ImportConfirm,
  type TemplateDraft, type DirectReadingWrite, type DirectReading,
  type UsageReviewResponse, type UsageReviewUpdate,
} from '@/lib/api/energy-ledger'

async function write<T>(path: string, payload: unknown, method = 'POST') {
  return actionResult(async () => {
    const headers = await getAuthHeaders()
    // Imports and reviews use the settings grant, not report grants.
    if (path.startsWith('/imports/') || path.startsWith('/usage-reviews')) headers['X-Dazah-Page-Path'] = '/energy/settings'
    const result = await ledgerRequest<T>(path, { method, body: JSON.stringify(payload) }, headers)
    revalidatePath('/energy', 'layout')
    return result
  })
}

async function actionResult<T>(action: () => Promise<T>): Promise<LedgerActionResult<T>> {
  try { return { ok: true, data: await action() } }
  catch (error) { return { ok: false, message: error instanceof EnergyLedgerRequestError ? error.message : '请求未完成，请稍后重试；本次输入已保留' } }
}
export async function saveLedgerBot(payload: BotWrite) {
  return write<Bot>('/bot-config', payload, 'PUT')
}
export async function retryLedgerNotification(id: string) {
  return write<Notification>(`/notification-runs/${encodeURIComponent(id)}/retry`, {})
}
export async function previewLedgerImport(formData: FormData) {
  const headers = await getAuthHeaders()
  headers['X-Dazah-Page-Path'] = '/energy/settings'
  delete headers['Content-Type']
  const query = new URLSearchParams()
  for (const key of ['year', 'start_date', 'end_date']) {
    const value = formData.get(key)
    if (typeof value === 'string' && value) query.set(key, value)
    formData.delete(key)
  }
  return actionResult(() => ledgerRequest<ImportPreview>(`/imports/preview?${query}`, { method: 'POST', body: formData }, headers))
}
export async function confirmLedgerImport(id: string, payload: ImportConfirm) {
  return write<ImportPreview>(`/imports/${encodeURIComponent(id)}/confirm`, payload)
}
export async function prepareLedgerImport(id: string) {
  return write<TemplateDraft>(`/imports/${encodeURIComponent(id)}/prepare`, {})
}
export async function saveUsageReviews(payload: UsageReviewUpdate) {
  return write<UsageReviewResponse[]>('/usage-reviews', payload, 'PUT')
}
export async function saveDirectReadings(payload: DirectReadingWrite) {
  return write<DirectReading>('/input-readings', payload, 'PUT')
}
