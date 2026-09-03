/**
 * 权限管理 - 服务器端 API（Server Component / Server Action 使用）
 * 使用 API_BASE_URL 环境变量（Docker 内部网络）
 */
import { cookies } from "next/headers"
import type { MenuFlatItem } from "@/lib/menu-tree"

const API_BASE =
  process.env.API_BASE_URL ||
  process.env.INTERNAL_API_BASE_URL ||
  "http://dazah-backend-app-1:8000"

export interface PermissionItem {
  id: string
  code: string
  module: string
  action: string
  name: string
  description?: string | null
}

export interface RoleItem {
  id: string
  name: string
  code: string
  description?: string | null
  is_system: boolean
  permissions: string[]
  grant_version?: number
}

export interface AdminUserItem {
  id: string
  name: string
  email?: string | null
  department?: string | null
  position?: string | null
  roles: RoleItem[]
}

export interface DeptRuleItem {
  id: string
  role_id: string
  role_name?: string | null
  role_code?: string | null
  feishu_department_id?: string | null
  department_name?: string | null
}

/** 部门扁平项（与后端 DepartmentResponse 字段对齐，用于数据范围配置的部门选择树） */
export interface DepartmentItem {
  id: string
  feishu_department_id: string
  name: string
  parent_feishu_department_id?: string | null
}

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

/** 服务端读取 auth_token cookie，供请求后端时携带 Bearer 认证头 */
async function getAuthHeaders(): Promise<Record<string, string> | undefined> {
  const cookieStore = await cookies()
  const token = cookieStore.get("auth_token")?.value
  return token ? { Authorization: `Bearer ${token}` } : undefined
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `请求失败 (${res.status})`
    try {
      const json = await res.json()
      if (json?.message) detail = json.message
    } catch {
      // ignore parse error
    }
    throw new Error(detail)
  }
  const json = (await res.json()) as ApiResponse<T>
  return json.data
}

export async function serverFetchPermissions(): Promise<PermissionItem[]> {
  const res = await fetch(`${API_BASE}/api/v1/identity/admin/permissions`, {
    cache: "no-store",
    headers: await getAuthHeaders(),
  })
  return handleResponse<PermissionItem[]>(res)
}

export async function serverFetchRoles(): Promise<RoleItem[]> {
  const res = await fetch(`${API_BASE}/api/v1/identity/admin/roles`, {
    cache: "no-store",
    headers: await getAuthHeaders(),
  })
  return handleResponse<RoleItem[]>(res)
}

export async function serverFetchDeptRules(): Promise<DeptRuleItem[]> {
  const res = await fetch(`${API_BASE}/api/v1/identity/admin/dept-rules`, {
    cache: "no-store",
    headers: await getAuthHeaders(),
  })
  return handleResponse<DeptRuleItem[]>(res)
}

export async function serverFetchDepartments(): Promise<DepartmentItem[]> {
  const res = await fetch(`${API_BASE}/api/v1/identity/departments`, {
    cache: "no-store",
    headers: await getAuthHeaders(),
  })
  return handleResponse<DepartmentItem[]>(res)
}

export async function serverFetchMenus(): Promise<MenuFlatItem[]> {
  const res = await fetch(`${API_BASE}/api/v1/identity/admin/menus`, {
    cache: "no-store",
    headers: await getAuthHeaders(),
  })
  return handleResponse<MenuFlatItem[]>(res)
}

/** 账号列表（含角色；权限验证台账号选择用） */
export async function serverFetchAdminUsers(): Promise<AdminUserItem[]> {
  const res = await fetch(`${API_BASE}/api/v1/identity/admin/users?limit=500`, {
    cache: "no-store",
    headers: await getAuthHeaders(),
  })
  const data = await handleResponse<{ items: AdminUserItem[]; total: number }>(res)
  return data.items ?? []
}
