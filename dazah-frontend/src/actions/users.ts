'use server'

import { getServerApiBaseUrl } from '@/lib/server-api'
import { getAuthHeaders } from '@/lib/auth'
import { revalidatePath } from 'next/cache'
import type { components } from '@/types/generated/schema'
import { permissionActionResult } from '@/lib/permission-action-result'

const API_BASE = getServerApiBaseUrl()

export type UserManagementItem = components['schemas']['UserManagementItem']
export type UserManagementListResponse =
  components['schemas']['UserManagementListResponse']
export type LocalUserCreate = components['schemas']['LocalUserCreate']
export type UserManagementUpdate = components['schemas']['UserManagementUpdate']
export type PasswordResetRequest = components['schemas']['PasswordResetRequest']
export type ModulePermissionGrantInput =
  components['schemas']['ModulePermissionGrantInput']
export type ModulePermissionGrantOut =
  components['schemas']['ModulePermissionGrantOut']
export type ModulePermissionDefinitionOut =
  components['schemas']['ModulePermissionDefinitionOut']
export type UserModulePermissionsOut =
  components['schemas']['UserModulePermissionsOut']
export type UserModulePermissionsUpdate =
  components['schemas']['UserModulePermissionsUpdate']
export type PermissionAuditItem = components['schemas']['PermissionAuditItem']
export type LivzonAccessScopeOut = components['schemas']['LivzonAccessScopeOut']
export type ModulePermissionKey = NonNullable<
  ModulePermissionGrantInput['permissions']
>[number]
export type PageGrantInput = components['schemas']['PageGrantInput']
export type PagePermissionDefinitionOut =
  components['schemas']['PagePermissionDefinitionOut']
export type EffectivePageGrantOut =
  components['schemas']['EffectivePageGrantOut']
export type UserPagePermissionsOut =
  components['schemas']['UserPagePermissionsOut']
export type UserPagePermissionsUpdate =
  components['schemas']['UserPagePermissionsUpdate']
export type PagePermissionHistoryItemOut =
  components['schemas']['PagePermissionHistoryItemOut']
export type PagePermissionHistoryPageOut =
  components['schemas']['PagePermissionHistoryPageOut']
export type PagePermissionRollbackRequest =
  components['schemas']['PagePermissionRollbackRequest']
export type PagePermissionRollbackPreviewRequest =
  components['schemas']['PagePermissionRollbackPreviewRequest']
export type PagePermissionRollbackPreviewOut =
  components['schemas']['PagePermissionRollbackPreviewOut']
export type DepartmentResponse = {
  id: string
  feishu_department_id: string
  name: string
  parent_feishu_department_id?: string | null
}

export type FeishuUserSyncResult = {
  status: 'ok' | 'warning'
  message: string
}

interface ApiEnvelope<T> {
  code?: number
  data?: T
  message?: string
  detail?: string
}

async function fetchIdentity<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const authHeaders = await getAuthHeaders()

  const res = await fetch(`${API_BASE}/api/v1/identity${endpoint}`, {
    ...options,
    headers: {
      ...authHeaders,
      ...options?.headers,
    },
    cache: 'no-store',
  })

  const json = (await res.json().catch(() => null)) as ApiEnvelope<T> | null
  if (!res.ok) {
    throw new Error(json?.detail || json?.message || `API error: ${res.status}`)
  }
  return (json?.data ?? json) as T
}

export async function getUsers(params?: {
  keyword?: string
  role?: 'admin' | 'user'
  status?: 'active' | 'disabled'
}) {
  const search = new URLSearchParams()
  if (params?.keyword) search.set('keyword', params.keyword)
  if (params?.role) search.set('role', params.role)
  if (params?.status) search.set('status', params.status)
  const query = search.toString()
  return fetchIdentity<UserManagementListResponse>(
    `/users${query ? `?${query}` : ''}`
  )
}

export async function syncFeishuUsers() {
  const result = await fetchIdentity<FeishuUserSyncResult>('/users/sync-feishu', {
    method: 'POST',
  })
  revalidatePath('/settings')
  return result
}

export async function createUser(data: LocalUserCreate) {
  const result = await fetchIdentity<UserManagementItem>('/users', {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/settings')
  return result
}

export async function updateUser(id: string, data: UserManagementUpdate) {
  const result = await fetchIdentity<UserManagementItem>(`/users/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath('/settings')
  return result
}

export async function resetUserPassword(id: string, data: PasswordResetRequest) {
  const result = await fetchIdentity<{ message: string }>(
    `/users/${id}/reset-password`,
    {
      method: 'POST',
      body: JSON.stringify(data),
    }
  )
  revalidatePath('/settings')
  return result
}

export async function getUserModulePermissions(id: string) {
  return fetchIdentity<UserModulePermissionsOut>(
    `/users/${id}/module-permissions`
  )
}

export async function replaceUserModulePermissions(
  id: string,
  data: UserModulePermissionsUpdate
) {
  const result = await fetchIdentity<UserModulePermissionsOut>(
    `/users/${id}/module-permissions`,
    {
      method: 'PUT',
      headers: {
        'If-Match': String(data.expected_grant_version),
      },
      body: JSON.stringify(data),
    }
  )
  revalidatePath('/settings')
  return result
}

export async function getUserPagePermissions(id: string) {
  return fetchIdentity<UserPagePermissionsOut>(
    `/admin/users/${id}/page-permissions`
  )
}

export async function replaceUserPagePermissions(
  id: string,
  data: UserPagePermissionsUpdate
) {
  const result = await permissionActionResult<UserPagePermissionsOut>(async () => fetch(
    `${API_BASE}/api/v1/identity/admin/users/${id}/page-permissions`, {
      method: 'PUT',
      headers: {
        ...await getAuthHeaders(),
        'Content-Type': 'application/json',
        'If-Match': String(data.expected_grant_version),
      },
      body: JSON.stringify(data),
    }
  ))
  if (result.ok) revalidatePath('/settings')
  return result
}

export type PagePermissionHistoryQuery = {
  actor_user_id?: string
  source?: 'manual' | 'rollback' | 'health_remediation'
  page_key?: string
  change_kind?: 'grant' | 'expand' | 'restrict' | 'revoke' | 'mixed'
  date_from?: string
  date_to?: string
  page?: number
  page_size?: number
}

function pagePermissionHistoryQuery(query: PagePermissionHistoryQuery = {}) {
  const params = new URLSearchParams()
  Object.entries(query).forEach(([key, value]) => {
    if (value) params.set(key, String(value))
  })
  const text = params.toString()
  return text ? `?${text}` : ''
}

export async function getUserPagePermissionHistory(
  id: string,
  query: PagePermissionHistoryQuery = {}
) {
  return fetchIdentity<PagePermissionHistoryPageOut>(
    `/admin/users/${id}/page-permissions/history${pagePermissionHistoryQuery(query)}`
  )
}

export async function previewUserPagePermissionRollback(
  id: string,
  data: PagePermissionRollbackPreviewRequest
) {
  return fetchIdentity<PagePermissionRollbackPreviewOut>(
    `/admin/users/${id}/page-permissions/rollback/preview`,
    { method: 'POST', body: JSON.stringify(data) }
  )
}

export async function exportUserPagePermissionHistory(id: string) {
  const res = await fetch(
    `${API_BASE}/api/v1/identity/admin/users/${id}/page-permissions/history/export`,
    { headers: await getAuthHeaders(), cache: 'no-store' }
  )
  if (!res.ok) {
    const json = (await res.json().catch(() => null)) as ApiEnvelope<unknown> | null
    throw new Error(json?.message || json?.detail || `请求失败 (${res.status})`)
  }
  return {
    filename: /filename="?([^";]+)"?/.exec(res.headers.get('Content-Disposition') ?? '')?.[1]
      ?? 'page-permission-history.csv',
    content: await res.text(),
  }
}

export async function rollbackUserPagePermissions(
  id: string,
  data: PagePermissionRollbackRequest
) {
  const result = await permissionActionResult<UserPagePermissionsOut>(async () => fetch(
    `${API_BASE}/api/v1/identity/admin/users/${id}/page-permissions/rollback`, {
      method: 'POST',
      headers: { ...await getAuthHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }
  ))
  if (result.ok) revalidatePath('/settings')
  return result
}

export async function getPermissionDepartments() {
  return fetchIdentity<DepartmentResponse[]>('/departments')
}

export async function getUserLivzonAccessScope(id: string) {
  return fetchIdentity<LivzonAccessScopeOut>(
    `/users/${id}/livzon-access-scope`
  )
}

export async function syncUserLivzonAccessScope(id: string) {
  const result = await fetchIdentity<LivzonAccessScopeOut>(
    `/users/${id}/livzon-access-scope/sync`,
    { method: 'POST' }
  )
  revalidatePath('/settings')
  return result
}

export async function getUserPermissionAudit(id: string, limit = 20) {
  return fetchIdentity<PermissionAuditItem[]>(
    `/users/${id}/permission-audit?limit=${limit}`
  )
}
