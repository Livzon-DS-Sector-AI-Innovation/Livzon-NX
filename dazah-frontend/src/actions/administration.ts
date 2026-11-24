'use server'

import { revalidatePath } from 'next/cache'

import { getAuthHeaders } from '@/lib/auth'
import { ADMIN_NOTICE_PAGE_KEY } from '@/lib/administration-pages'
import type {
  FeishuConfig,
  FeishuConfigInput,
  FeishuPageBinding,
} from '@/lib/feishu-data-source'
import { serverApiUrl } from '@/lib/server-api'
import type { NoticeItem, NoticeParsePreview } from '@/types/administration'

/**
 * 行政管理模块 Server Actions（写操作）。
 *
 * 飞书设置页的凭证保存、数据入口维护、同步与页面绑定都经此转发，
 * 统一携带设置页的页面上下文，后端按 admin:feishu-settings 校验操作权限。
 */

const SETTINGS_PAGE_KEY = 'admin:feishu-settings'
const SETTINGS_PATH = '/admin/settings/feishu'

type RootInput = {
  name: string
  source_type: 'wiki' | 'base'
  source_url: string
}

type ConnectivityResult = {
  ok: boolean
  steps: Array<{ name: string; status: string; message: string }>
}

async function settingsFetch(path: string, init: RequestInit): Promise<unknown> {
  const authHeaders = await getAuthHeaders()
  const response = await fetch(serverApiUrl(`/administration${path}`), {
    ...init,
    headers: { ...authHeaders, 'X-Dazah-Page-Key': SETTINGS_PAGE_KEY },
    cache: 'no-store',
  })
  const body = (await response.json().catch(() => null)) as {
    message?: string
    detail?: string | { message?: string }
    data?: unknown
  } | null
  if (!response.ok) {
    const detail = typeof body?.detail === 'string' ? body.detail : body?.detail?.message
    throw new Error(body?.message || detail || `请求失败（${response.status}）`)
  }
  return body?.data ?? null
}

export async function saveAdministrationFeishuConfigAction(
  values: FeishuConfigInput,
): Promise<FeishuConfig> {
  const result = (await settingsFetch('/feishu-config', {
    method: 'PUT',
    body: JSON.stringify(values),
  })) as FeishuConfig
  revalidatePath(SETTINGS_PATH)
  return result
}

export async function testAdministrationFeishuConfigAction(
  values: FeishuConfigInput,
): Promise<ConnectivityResult> {
  return (await settingsFetch('/feishu-config/test', {
    method: 'POST',
    body: JSON.stringify(values),
  })) as ConnectivityResult
}

export async function createAdministrationFeishuRootAction(values: RootInput): Promise<unknown> {
  const result = await settingsFetch('/feishu-read/roots', {
    method: 'POST',
    body: JSON.stringify(values),
  })
  revalidatePath(SETTINGS_PATH)
  return result
}

export async function deleteAdministrationFeishuRootAction(rootId: string): Promise<unknown> {
  const result = await settingsFetch(`/feishu-read/roots/${encodeURIComponent(rootId)}`, {
    method: 'DELETE',
  })
  revalidatePath(SETTINGS_PATH)
  return result
}

export async function discoverAdministrationFeishuRootAction(rootId: string): Promise<unknown> {
  const result = await settingsFetch(
    `/feishu-read/roots/${encodeURIComponent(rootId)}/discover`,
    { method: 'POST' },
  )
  revalidatePath(SETTINGS_PATH)
  return result
}

export async function syncAdministrationFeishuResourceAction(
  resourceId: string,
): Promise<unknown> {
  const result = await settingsFetch(
    `/feishu-read/resources/${encodeURIComponent(resourceId)}/sync`,
    { method: 'POST' },
  )
  revalidatePath('/admin/tobacco-gift', 'layout')
  return result
}

export async function syncAdministrationFeishuResourcesAction(
  resourceIds: string[],
): Promise<unknown> {
  const results = []
  // 顺序同步：平台镜像服务按数据表加 Redis 锁，避免并发撞锁返回 409。
  for (const resourceId of resourceIds) {
    results.push(await syncAdministrationFeishuResourceAction(resourceId))
  }
  return results
}

export async function saveAdministrationPageBindingsAction(
  pageKey: string,
  bindings: FeishuPageBinding[],
): Promise<unknown> {
  const result = await settingsFetch(
    `/feishu-read/page-bindings/${encodeURIComponent(pageKey)}`,
    { method: 'PUT', body: JSON.stringify({ bindings }) },
  )
  revalidatePath('/admin/tobacco-gift', 'layout')
  return result
}

/** 仪表台页上下文：AI 分析按仪表台页面授权（operate）校验。 */
const DASHBOARD_PAGE_KEY = 'admin:tobacco-gift:dashboard'

export type TobaccoGiftAiAnalysisAction = {
  summary: string
  insights: string[]
  anomalies: string[]
  suggestions: string[]
  generated_at: string
}

export async function generateTobaccoGiftAiAnalysisAction(): Promise<
  | { ok: true; data: TobaccoGiftAiAnalysisAction }
  | { ok: false; message: string }
> {
  const authHeaders = await getAuthHeaders()
  const response = await fetch(serverApiUrl('/administration/tobacco-gift/ai-analysis'), {
    method: 'POST',
    headers: { ...authHeaders, 'X-Dazah-Page-Key': DASHBOARD_PAGE_KEY },
    cache: 'no-store',
  })
  const body = (await response.json().catch(() => null)) as {
    message?: string
    detail?: string | { message?: string }
    data?: TobaccoGiftAiAnalysisAction
  } | null
  if (!response.ok || !body?.data) {
    const detail = typeof body?.detail === 'string' ? body.detail : body?.detail?.message
    const message = body?.message || detail || `AI 分析生成失败（${response.status}）`
    // 结构化结果跨 Server Action 边界不会被掩盖；文案为后端策划的安全提示
    return { ok: false, message }
  }
  return { ok: true, data: body.data }
}

// ── 公告通知台账（平台原生；上传经 Server Action 转发 multipart） ──

const NOTICE_PAGE_KEY = ADMIN_NOTICE_PAGE_KEY
const NOTICE_PATH = '/admin/notice'

type NoticeActionEnvelope<T> = {
  code: number
  message?: string
  data?: T
}

/** 公告上传通道：FormData 转发须剥离自动 Content-Type（让浏览器带 boundary）。 */
async function noticeUploadFetch<T>(
  path: string,
  file: File,
  fields: Record<string, string> = {},
): Promise<NoticeActionEnvelope<T>> {
  const formData = new FormData()
  formData.append('file', file)
  for (const [key, value] of Object.entries(fields)) {
    if (value !== '') formData.append(key, value)
  }
  const authHeaders = await getAuthHeaders()
  const uploadHeaders: Record<string, string> = { ...authHeaders }
  // multipart 转发必须剥离自动 Content-Type（让浏览器带 boundary）
  delete uploadHeaders['Content-Type']
  uploadHeaders['X-Dazah-Page-Key'] = NOTICE_PAGE_KEY
  let response: Response
  try {
    response = await fetch(serverApiUrl(`/administration${path}`), {
      method: 'POST',
      headers: uploadHeaders,
      body: formData,
    })
  } catch {
    return { code: -1, message: '网络请求失败，无法连接到后端服务' }
  }
  const body = (await response.json().catch(() => null)) as {
    message?: string
    detail?: string | { message?: string }
    data?: T
  } | null
  if (!response.ok || body === null) {
    const detail = typeof body?.detail === 'string' ? body.detail : body?.detail?.message
    return {
      code: response.status,
      message: detail || body?.message || `请求失败（${response.status}）`,
    }
  }
  return { code: 200, data: body.data }
}

/** AI 识别公告元数据（预览不落库，响应不含公告内容）。 */
export async function parseNoticeAction(
  file: File,
): Promise<NoticeActionEnvelope<NoticeParsePreview>> {
  return noticeUploadFetch<NoticeParsePreview>('/notices/parse', file)
}

/** 确认导入公告（原文存档 + AI 提取正文；元数据以确认值为准）。 */
export async function importNoticeAction(
  file: File,
  fields: {
    notice_no: string
    title: string
    publisher: string
    published_at: string
    category: string
    remark: string
  },
): Promise<NoticeActionEnvelope<NoticeItem>> {
  const result = await noticeUploadFetch<NoticeItem>('/notices', file, { ...fields })
  revalidatePath(NOTICE_PATH)
  return result
}
