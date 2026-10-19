'use server'

import { revalidatePath } from 'next/cache'
import { getAuthHeaders } from '@/lib/auth'
import {
  ledgerRequest, EnergyLedgerRequestError, type LedgerActionResult, type MeterWrite, type Meter, type RuleWrite, type Rule,
  type PlanWrite, type Plan, type EntrySubmission, type Task, type TaskList,
  type LockWrite, type Lock, type BotWrite, type Bot, type Notification,
  type ImportPreview, type ImportConfirm, type AdjustmentWrite, type UsageRow,
  type Report, type Trial, type TemplateDraft, type SnapshotImportRequest,
} from '@/lib/api/energy-ledger'

async function write<T>(path: string, payload: unknown, method = 'POST') {
  return actionResult(async () => {
    const result = await ledgerRequest<T>(path, { method, body: JSON.stringify(payload) }, await getAuthHeaders())
    revalidatePath('/energy', 'layout')
    return result
  })
}

async function actionResult<T>(action: () => Promise<T>): Promise<LedgerActionResult<T>> {
  try { return { ok: true, data: await action() } }
  catch (error) { return { ok: false, message: error instanceof EnergyLedgerRequestError ? error.message : '请求未完成，请稍后重试；本次输入已保留' } }
}

export async function saveLedgerMeter(id: string | null, payload: MeterWrite) {
  return write<Meter>(id ? `/meter-points/${encodeURIComponent(id)}` : '/meter-points', payload, id ? 'PUT' : 'POST')
}
export async function saveLedgerRule(id: string | null, payload: RuleWrite) {
  return write<Rule>(id ? `/calculation-rules/${encodeURIComponent(id)}` : '/calculation-rules', payload, id ? 'PUT' : 'POST')
}
export async function saveLedgerPlan(id: string | null, payload: PlanWrite) {
  return write<Plan>(id ? `/entry-plans/${encodeURIComponent(id)}` : '/entry-plans', payload, id ? 'PUT' : 'POST')
}
export async function submitLedgerTask(id: string, payload: EntrySubmission) {
  return write<Task>(`/entry-tasks/${encodeURIComponent(id)}/submit`, payload)
}
export async function generateLedgerTasks(taskDate: string) {
  return write<TaskList>('/entry-tasks/generate', { task_date: taskDate })
}
export async function saveLedgerLock(month: string, payload: LockWrite) {
  return write<Lock>(`/period-locks/${encodeURIComponent(month)}`, payload, 'PUT')
}
export async function saveLedgerBot(payload: BotWrite) {
  return write<Bot>('/bot-config', payload, 'PUT')
}
export async function retryLedgerNotification(id: string) {
  return write<Notification>(`/notification-runs/${encodeURIComponent(id)}/retry`, {})
}
export async function previewLedgerImport(formData: FormData) {
  const headers = await getAuthHeaders()
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
export async function createLedgerTemplateDraft(id: string) {
  return write<TemplateDraft>(`/imports/${encodeURIComponent(id)}/draft-config`, {})
}
export async function previewLedgerSnapshots(payload: SnapshotImportRequest) {
  return write<ImportPreview>('/imports/from-snapshot', payload)
}
export async function adjustLedgerUsage(payload: AdjustmentWrite) {
  return write<UsageRow>('/adjustments', payload)
}
export async function rebuildLedgerReports(startDate: string, endDate: string) {
  return write<Report>('/reporting/rebuild', { start_date: startDate, end_date: endDate })
}
export async function trialLedgerRules(usageDate: string) {
  return write<Trial>('/calculation-rules/trial', { usage_date: usageDate })
}
