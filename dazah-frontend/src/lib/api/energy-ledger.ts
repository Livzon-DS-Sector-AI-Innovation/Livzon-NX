import type { components } from '@/types/generated/schema'
import { serverApiUrl } from '@/lib/server-api'

type Schema = components['schemas']
export type LedgerActionResult<T> = { ok: true; data: T } | { ok: false; message: string }
export class EnergyLedgerRequestError extends Error {}

export async function resolveLedgerAction<T>(promise: Promise<LedgerActionResult<T>>): Promise<T> {
  const result = await promise
  if (!result.ok) throw new Error(result.message)
  return result.data
}
export type MeterWrite = Schema['MeterWrite']
export type Meter = Schema['MeterResponse']
export type RuleWrite = Schema['RuleWrite']
export type Rule = Schema['RuleResponse']
export type PlanWrite = Schema['PlanWrite']
export type Plan = Schema['PlanResponse']
export type Task = Schema['TaskResponse']
export type EntryItem = Schema['EntryItemResponse']
export type EntrySubmission = Schema['EntrySubmission']
export type Report = Schema['ReportResponse']
export type UsageRow = Schema['UsageRow']
export type Options = Schema['LedgerOptions']
export type TaskList = Schema['TaskListResponse']
export type Lock = Schema['LockResponse']
export type LockWrite = Schema['LockWrite']
export type Bot = Schema['BotResponse']
export type BotWrite = Schema['BotWrite']
export type Notification = Schema['NotificationResponse']
export type ImportPreview = Schema['ImportResponse']
export type ImportConfirm = Schema['ImportConfirm']
export type AdjustmentWrite = Schema['AdjustmentWrite']
export type Revision = Schema['RevisionResponse']
export type Trial = Schema['TrialResponse']
export type TemplateDraft = Schema['TemplateDraftResponse']
export type SnapshotOption = Schema['SnapshotImportOption']
export type SnapshotImportRequest = Schema['SnapshotImportRequest']
export type WorkbookDataset = Schema['WorkbookDataset']
export type WorkbookReport = Schema['WorkbookReport']
export type WorkbookCell = Schema['WorkbookCell']
export type EnergyMetricOption = Schema['EnergyMetricOption']

export async function ledgerRequest<T>(path: string, init?: RequestInit, auth?: Record<string, string>): Promise<T> {
  const url = `/api/v1/energy${path}`
  const headers = new Headers(auth)
  if (!(init?.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  if (typeof window !== 'undefined') headers.set('X-Dazah-Page-Path', window.location.pathname)
  new Headers(init?.headers).forEach((value, key) => headers.set(key, value))
  const response = await fetch(typeof window === 'undefined' ? serverApiUrl(url) : url, { ...init, headers, cache: 'no-store' })
  const body: unknown = await response.json()
  if (!response.ok) {
    const message = body && typeof body === 'object' && 'message' in body && typeof body.message === 'string' ? body.message : `请求未完成（${response.status}），请检查输入或权限`
    throw new EnergyLedgerRequestError(message)
  }
  // All callers use generated endpoint response types; the HTTP envelope is shared.
  return (body as { data: T }).data
}

export function reportQuery(params: Record<string, string | number | undefined>) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => { if (value !== undefined && value !== '') query.set(key, String(value)) })
  return query.toString()
}

export const CATEGORY_LABELS = {
  drinking_water: '饮用水', chilled_water: '冰水', steam: '蒸汽',
  circulating_water: '循环水', air: '压缩空气', electricity: '电量',
} as const

export const QUALITY_LABELS: Record<string, string> = {
  complete: '完整', partial: '部分数据', pending: '待计算', adjusted: '已调整',
  missing_reading: '缺少读数', missing_dependency: '计算缺项', reading_rollback: '读数回退',
  invalid_meter_event: '换表记录无效', zero_denominator: '分母为零',
  abnormal_usage: '用量超出阈值', abnormal_dependency: '来源存在异常',
  out_of_range: '计算值超出计量范围', late_submission: '逾期补填',
  unconfigured: '待确认配置', not_applicable: '不适用', configuration_conflict: '配置冲突',
}

export function taskChanges(task: Task, values: Record<string, string | undefined>): EntrySubmission['values'] {
  return task.items.flatMap(item => {
    const value = values[item.id] ?? item.draft_value
    return value !== undefined && value !== null && value !== '' ? [{ reading_id: item.id, version: item.version, value }] : []
  })
}

export function formatAmount(value: string | number | null | undefined) {
  if (value === null || value === undefined) return '—'
  const text = String(value)
  if (/^[-+]?0(?:\.0+)?(?:e[-+]?\d+)?$/i.test(text)) return '0'
  return text.includes('.') && !/[eE]/.test(text) ? text.replace(/0+$/, '').replace(/\.$/, '') : text
}

export function estimateUsage(value: string | undefined, previous: string | null, multiplier: string, direct: boolean): string | undefined {
  const scale = BigInt(100000000)
  function fixed(input: string): bigint | undefined {
    if (/^0(?:\.0+)?(?:e[-+]?\d+)?$/i.test(input)) return BigInt(0)
    if (!/^\d+(?:\.\d{1,8})?$/.test(input)) return undefined
    const [whole, decimals = ''] = input.split('.')
    return BigInt(whole) * scale + BigInt(decimals.padEnd(8, '0'))
  }
  const after = value === undefined ? undefined : fixed(value)
  const before = direct ? BigInt(0) : previous === null ? undefined : fixed(previous)
  const factor = fixed(multiplier)
  if (after === undefined || before === undefined || factor === undefined || after < before) return undefined
  const result = (after - before) * factor
  const squared = scale * scale
  return formatAmount(`${result / squared}.${String(result % squared).padStart(16, '0')}`)
}
