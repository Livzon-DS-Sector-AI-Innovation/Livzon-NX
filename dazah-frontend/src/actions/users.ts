'use server'

import { getServerApiBaseUrl } from '@/lib/server-api'
import { getAuthHeaders } from '@/lib/auth'
import { revalidatePath } from 'next/cache'
import type { components } from '@/types/generated/schema'

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
