import { moduleMenus, type SubMenuItem } from '@/lib/menu-config'
import type { components } from '@/types/generated/schema'

export type FeishuModuleCode = 'production' | 'energy' | 'warehouse'

export type FeishuConfig = {
  id?: string | null
  config_name: string
  app_id: string
  app_secret_configured: boolean
  app_secret_masked?: string
  is_active: boolean
  timezone?: string
  daily_sync_time?: string
  remark?: string | null
}

export type FeishuConfigInput = {
  id?: string | null
  config_name: string
  app_id: string
  app_secret?: string
  is_active: boolean
  timezone: string
  daily_sync_time: string
  remark?: string | null
}

export type FeishuSourceRoot = {
  id: string
  name: string
  source_type: 'wiki' | 'base'
  source_url: string
  discovery_status: string
  discovery_error?: string | null
  last_discovered_at?: string | null
}

export type FeishuResource = {
  id: string
  title: string
  table_id: string
  source_path: Array<{ title?: string }>
  field_count: number
  record_count: number
  sync_status: string
  sync_error?: string | null
  last_complete_sync_at?: string | null
}

export type FeishuPageBinding = {
  resource_id: string
  tab_name: string
  sort_order: number
  is_default: boolean
  is_enabled: boolean
  visible_field_ids: string[]
}

export type FeishuPageOption = { label: string; value: string }

export type FeishuMappedMenuTarget = FeishuPageOption & {
  path: string
}

export type FeishuResourceDeleteResult = components['schemas']['EnergySourceDeleteResult']
type EnergySourceBatchRequest = components['schemas']['EnergySourceBatchRequest']

type ApiEnvelope<T> = {
  code?: number
  message?: string
  detail?: string | { message?: string }
  error?: { message?: string }
  data: T
}

async function api<T>(moduleCode: FeishuModuleCode, path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1/${moduleCode}${path}`, {
    ...init,
    cache: 'no-store',
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
  })
  const body = await response.json().catch(() => null) as ApiEnvelope<T> | null
  if (!response.ok || !body) {
    const detail = typeof body?.detail === 'string' ? body.detail : body?.detail?.message
    throw new Error(body?.message || detail || body?.error?.message || `请求失败（${response.status}）`)
  }
  return body.data
}

function mappedMenuTargets(moduleCode: FeishuModuleCode): FeishuMappedMenuTarget[] {
  const menu = moduleMenus.find((item) => item.moduleCode === moduleCode)
  if (!menu) return []

  const pages: FeishuMappedMenuTarget[] = []
  const normalizeKey = (value: string) => value.replace(/[^\p{L}\p{N}_-]+/gu, '_')
  const visit = (items: SubMenuItem[], parentLabels: string[], parentKeys: string[]) => {
    items.forEach((item) => {
      const labels = [...parentLabels, item.label.replace('（开发中）', '')]
      const keys = [...parentKeys, item.key]
      const isConfigPage = item.key === 'feishu-config' || item.path.endsWith('/feishu-config')
      const isNavigablePage = Boolean(item.path && item.path !== '#' && !item.disabled && !isConfigPage)

      if (isNavigablePage) {
        pages.push({
          label: labels.join(' / '),
          value: item.feishuPageKey || `${moduleCode}.${keys.map(normalizeKey).join('.')}`,
          path: item.path,
        })
      }
      if (item.children?.length) visit(item.children, labels, keys)
    })
  }

  visit(menu.children, [], [])
  return pages
}

function pageOptions(moduleCode: FeishuModuleCode): FeishuPageOption[] {
  return mappedMenuTargets(moduleCode).map(({ label, value }) => ({ label, value }))
}

/**
 * Resolve the currently selected recursive menu leaf to the exact page key used
 * by the Feishu mapping configuration. Query parameters declared by a menu item
 * participate in matching, while display-state parameters such as `dataset` do
 * not affect the result.
 */
export function getFeishuMappedMenuTarget(
  moduleCode: FeishuModuleCode,
  pathname: string,
  searchParams: Pick<URLSearchParams, 'get'>,
): FeishuMappedMenuTarget | undefined {
  const candidates = mappedMenuTargets(moduleCode).filter((target) => {
    const [targetPathname, queryString = ''] = target.path.split('?')
    if (pathname !== targetPathname) return false
    const expected = new URLSearchParams(queryString)
    for (const [key, value] of expected.entries()) {
      if (searchParams.get(key) !== value) return false
    }
    return true
  })

  return candidates.sort((left, right) => {
    const leftQuerySize = new URLSearchParams(left.path.split('?')[1] || '').size
    const rightQuerySize = new URLSearchParams(right.path.split('?')[1] || '').size
    return rightQuerySize - leftQuerySize || right.path.length - left.path.length
  })[0]
}

function rootsPath(moduleCode: FeishuModuleCode) {
  return moduleCode === 'production' ? '/feishu-read/roots' : '/feishu/roots'
}

function normalizeResource(item: Record<string, unknown>): FeishuResource {
  const headers = Array.isArray(item.headers) ? item.headers : []
  return {
    id: String(item.id || ''),
    title: String(item.title || item.name || '未命名数据表'),
    table_id: String(item.table_id || item.external_sheet_id || ''),
    source_path: Array.isArray(item.source_path)
      ? item.source_path as Array<{ title?: string }>
      : item.document_title ? [{ title: String(item.document_title) }] : [],
    field_count: Number(item.field_count ?? headers.length ?? 0),
    record_count: Number(item.record_count ?? 0),
    sync_status: String(item.sync_status || (item.last_synced_at ? 'success' : 'pending')),
    sync_error: typeof item.sync_error === 'string' ? item.sync_error : null,
    last_complete_sync_at: String(item.last_complete_sync_at || item.last_synced_at || '') || null,
  }
}

export function getFeishuModuleDefinition(moduleCode: FeishuModuleCode) {
  const menu = moduleMenus.find((item) => item.moduleCode === moduleCode)
  if (!menu) throw new Error(`未注册模块：${moduleCode}`)
  return { moduleCode, moduleLabel: menu.label, pages: pageOptions(moduleCode) }
}

export const feishuDataSourceApi = {
  getConfig: (moduleCode: FeishuModuleCode) => api<FeishuConfig>(moduleCode, '/feishu-config'),

  saveConfig: (moduleCode: FeishuModuleCode, values: FeishuConfigInput) =>
    api<FeishuConfig>(moduleCode, '/feishu-config', {
      method: 'PUT',
      body: JSON.stringify(values),
    }),

  testConfig: (moduleCode: FeishuModuleCode, values: FeishuConfigInput) =>
    api<{ ok: boolean; steps: Array<{ name: string; status: string; message: string }> }>(
      moduleCode,
      '/feishu-config/test',
      { method: 'POST', body: moduleCode === 'energy' ? undefined : JSON.stringify(values) },
    ),

  listRoots: (moduleCode: FeishuModuleCode, configId?: string | null) =>
    api<FeishuSourceRoot[]>(moduleCode, `${rootsPath(moduleCode)}${moduleCode === 'production' && configId ? `?config_id=${encodeURIComponent(configId)}` : ''}`),

  createRoot: (
    moduleCode: FeishuModuleCode,
    payload: { name: string; source_type: 'wiki' | 'base'; source_url: string },
    configId?: string | null,
  ) => api<FeishuSourceRoot>(moduleCode, rootsPath(moduleCode), {
    method: 'POST',
    body: JSON.stringify({ ...payload, config_id: configId || undefined }),
  }),

  deleteRoot: (moduleCode: FeishuModuleCode, rootId: string) =>
    api(moduleCode, `${rootsPath(moduleCode)}/${rootId}`, { method: 'DELETE' }),

  discoverRoot: async (moduleCode: FeishuModuleCode, rootId: string) => {
    if (moduleCode === 'energy') {
      await api(moduleCode, '/sync-runs', { method: 'POST', body: JSON.stringify({ force: true }) })
      return
    }
    await api(moduleCode, `${rootsPath(moduleCode)}/${rootId}/discover`, { method: 'POST' })
  },

  listResources: async (moduleCode: FeishuModuleCode): Promise<FeishuResource[]> => {
    const path = moduleCode === 'production'
      ? '/feishu-read/resources'
      : moduleCode === 'warehouse' ? '/feishu/tables' : '/sources'
    const items = await api<Array<Record<string, unknown>>>(moduleCode, path)
    return items.map(normalizeResource)
  },

  syncResource: async (moduleCode: FeishuModuleCode, resourceId: string) => {
    if (moduleCode === 'energy') {
      await api(moduleCode, '/sync-runs', { method: 'POST', body: JSON.stringify({ force: true }) })
      return
    }
    const path = moduleCode === 'production'
      ? `/feishu-read/resources/${resourceId}/sync`
      : `/feishu/tables/${resourceId}/sync`
    await api(moduleCode, path, { method: 'POST' })
  },

  syncResources: async (moduleCode: FeishuModuleCode, resourceIds: string[]) => {
    if (moduleCode === 'energy') {
      const payload: EnergySourceBatchRequest = { sheet_ids: resourceIds }
      await api(moduleCode, '/sources/batch-sync', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      return
    }
    await Promise.all(resourceIds.map((resourceId) =>
      feishuDataSourceApi.syncResource(moduleCode, resourceId),
    ))
  },

  deleteResources: (moduleCode: FeishuModuleCode, resourceIds: string[]) => {
    if (moduleCode !== 'energy') throw new Error('当前模块暂不支持删除资源目录')
    const payload: EnergySourceBatchRequest = { sheet_ids: resourceIds }
    return api<FeishuResourceDeleteResult>(moduleCode, '/sources/batch', {
      method: 'DELETE',
      body: JSON.stringify(payload),
    })
  },

  getBindings: async (moduleCode: FeishuModuleCode, pageKey: string): Promise<FeishuPageBinding[]> => {
    const data = await api<{ bindings?: Array<Record<string, unknown>> }>(moduleCode, `/page-data/${encodeURIComponent(pageKey)}`)
    return (data.bindings || []).map((item, index) => ({
      resource_id: String(item.resource_id || item.table_pk || item.id || ''),
      tab_name: String(item.tab_name || item.tab_label || `数据表 ${index + 1}`),
      sort_order: Number(item.sort_order ?? item.display_order ?? index),
      is_default: Boolean(item.is_default),
      is_enabled: item.is_enabled !== false,
      visible_field_ids: Array.isArray(item.visible_field_ids) ? item.visible_field_ids.map(String) : [],
    })).filter((item) => item.resource_id)
  },

  saveBindings: async (moduleCode: FeishuModuleCode, pageKey: string, bindings: FeishuPageBinding[]) => {
    const path = moduleCode === 'production'
      ? `/feishu-read/page-bindings/${encodeURIComponent(pageKey)}`
      : `/page-data/${encodeURIComponent(pageKey)}`
    const normalized = moduleCode === 'warehouse'
      ? bindings.map((item) => ({
        table_pk: item.resource_id,
        tab_label: item.tab_name,
        display_order: item.sort_order,
        is_default: item.is_default,
        is_enabled: item.is_enabled,
        visible_field_ids: item.visible_field_ids,
        default_sort: [],
        history_mode: 'current_mirror',
      }))
      : bindings
    await api(moduleCode, path, { method: 'PUT', body: JSON.stringify({ bindings: normalized }) })
  },
}
