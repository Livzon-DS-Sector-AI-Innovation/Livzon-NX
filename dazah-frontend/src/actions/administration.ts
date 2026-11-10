'use server'

import { revalidatePath } from 'next/cache'

import { getAuthHeaders } from '@/lib/auth'
import type {
  FeishuConfig,
  FeishuConfigInput,
  FeishuPageBinding,
} from '@/lib/feishu-data-source'
import { serverApiUrl } from '@/lib/server-api'

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
