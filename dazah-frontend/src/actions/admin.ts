"use server"

import { cookies } from "next/headers"
import { revalidatePath } from "next/cache"
import type { components } from "@/types/generated/schema"

const API_BASE =
  process.env.API_BASE_URL ||
  process.env.INTERNAL_API_BASE_URL ||
  "http://dazah-backend-app-1:8000"

// API 类型从 generated schema 导入（前端规范§类型系统）
type RoleCreateRequest = components["schemas"]["RoleCreateRequest"]
type RoleUpdateRequest = components["schemas"]["RoleUpdateRequest"]
type RolePermissionsRequest = components["schemas"]["RolePermissionsRequest"]
type AssignUserRoleRequest = components["schemas"]["AssignUserRoleRequest"]
type DeptRuleCreateRequest = components["schemas"]["DeptRuleCreateRequest"]
type MenuCreateRequest = components["schemas"]["MenuCreateRequest"]
type MenuUpdateRequest = components["schemas"]["MenuUpdateRequest"]
type RoleMenusRequest = components["schemas"]["RoleMenusRequest"]
type DataScopeRuleCreateRequest = components["schemas"]["DataScopeRuleCreateRequest"]
type PermissionSimulateRequest = components["schemas"]["PermissionSimulateRequest"]

/**
 * 权限管理 Server Actions（写操作）。
 * 所有写操作必须通过本文件（前端规范§写操作必须用 Server Actions）。
 * 认证：读取 auth_token cookie 并携带 Bearer 头转发。
 */

async function authedFetch(path: string, init?: RequestInit): Promise<Response> {
  const cookieStore = await cookies()
  const token = cookieStore.get("auth_token")
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> | undefined),
  }
  if (token?.value) {
    headers["Authorization"] = `Bearer ${token.value}`
  }
  // 无 token 时不拦截：交由后端鉴权（开发免登录模式后端放行；
  // 生产环境后端返回 401 → handleResponse 抛出"未登录或登录已过期"），
  // 与 getCurrentUser 的免登录降级策略保持一致
  return fetch(`${API_BASE}/api/v1${path}`, { ...init, headers })
}

async function handleResponse(res: Response): Promise<unknown> {
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
  try {
    const json = await res.json()
    return json.data
  } catch {
    return null
  }
}

// ── 角色 ────────────────────────────────────────────────────────────

export async function createRole(data: RoleCreateRequest) {
  const res = await authedFetch("/identity/admin/roles", {
    method: "POST",
    body: JSON.stringify(data),
  })
  const result = await handleResponse(res)
  revalidatePath("/system/roles")
  return result
}

export async function updateRole(
  roleId: string,
  data: RoleUpdateRequest
) {
  const res = await authedFetch(`/identity/admin/roles/${roleId}`, {
    method: "PUT",
    body: JSON.stringify(data),
  })
  const result = await handleResponse(res)
  revalidatePath("/system/roles")
  return result
}

export async function deleteRole(roleId: string) {
  const res = await authedFetch(`/identity/admin/roles/${roleId}`, {
    method: "DELETE",
  })
  const result = await handleResponse(res)
  revalidatePath("/system/roles")
  return result
}

export async function setRolePermissions(roleId: string, permissionIds: string[]) {
  const body: RolePermissionsRequest = { permission_ids: permissionIds }
  const res = await authedFetch(`/identity/admin/roles/${roleId}/permissions`, {
    method: "POST",
    body: JSON.stringify(body),
  })
  const result = await handleResponse(res)
  revalidatePath("/system/roles")
  return result
}

// ── 用户角色 ────────────────────────────────────────────────────────

export async function assignUserRoles(userId: string, roleIds: string[]) {
  const body: AssignUserRoleRequest = { role_ids: roleIds }
  const res = await authedFetch(`/identity/admin/users/${userId}/roles`, {
    method: "POST",
    body: JSON.stringify(body),
  })
  const result = await handleResponse(res)
  revalidatePath("/system/user-roles")
  return result
}

export async function removeUserRole(userId: string, roleId: string) {
  const res = await authedFetch(`/identity/admin/users/${userId}/roles/${roleId}`, {
    method: "DELETE",
  })
  const result = await handleResponse(res)
  revalidatePath("/system/user-roles")
  return result
}

// ── 部门角色映射 ────────────────────────────────────────────────────

export async function createDeptRule(data: DeptRuleCreateRequest) {
  const res = await authedFetch("/identity/admin/dept-rules", {
    method: "POST",
    body: JSON.stringify(data),
  })
  const result = await handleResponse(res)
  revalidatePath("/system/dept-roles")
  return result
}

export async function deleteDeptRule(ruleId: string) {
  const res = await authedFetch(`/identity/admin/dept-rules/${ruleId}`, {
    method: "DELETE",
  })
  const result = await handleResponse(res)
  revalidatePath("/system/dept-roles")
  return result
}

// ── 菜单管理 ────────────────────────────────────────────────────────

export async function createMenu(data: MenuCreateRequest) {
  const res = await authedFetch("/identity/admin/menus", {
    method: "POST",
    body: JSON.stringify(data),
  })
  const result = await handleResponse(res)
  revalidatePath("/system/menus")
  return result
}

export async function updateMenu(menuId: string, data: MenuUpdateRequest) {
  const res = await authedFetch(`/identity/admin/menus/${menuId}`, {
    method: "PUT",
    body: JSON.stringify(data),
  })
  const result = await handleResponse(res)
  revalidatePath("/system/menus")
  return result
}

export async function deleteMenu(menuId: string) {
  const res = await authedFetch(`/identity/admin/menus/${menuId}`, {
    method: "DELETE",
  })
  const result = await handleResponse(res)
  revalidatePath("/system/menus")
  return result
}

// ── 角色菜单绑定 ────────────────────────────────────────────────────

export async function setRoleMenus(roleId: string, menuIds: string[]) {
  const body: RoleMenusRequest = { menu_ids: menuIds }
  const res = await authedFetch(`/identity/admin/roles/${roleId}/menus`, {
    method: "PUT",
    body: JSON.stringify(body),
  })
  const result = await handleResponse(res)
  revalidatePath("/system/roles")
  return result
}

// ── 数据范围配置（可见部门，后台可配置不写死）─────────────────────────

/**
 * 保存角色可见部门配置（同一角色仅一条，已存在则覆盖）。
 * scopeType=all 表示全部部门；departments 表示指定部门列表。
 */
export async function saveRoleDataScope(
  roleId: string,
  scopeType: "all" | "departments",
  departmentNames: string[],
) {
  const body: DataScopeRuleCreateRequest = {
    role_id: roleId,
    scope_type: scopeType,
    department_names: scopeType === "departments" ? departmentNames : null,
  }
  const res = await authedFetch("/identity/admin/data-scopes", {
    method: "POST",
    body: JSON.stringify(body),
  })
  const result = await handleResponse(res)
  revalidatePath("/system/roles")
  return result
}

/** 保存用户可见部门配置（个例覆盖，如高管；已存在则覆盖） */
export async function saveUserDataScope(
  userId: string,
  scopeType: "all" | "departments",
  departmentNames: string[],
) {
  const body: DataScopeRuleCreateRequest = {
    user_id: userId,
    scope_type: scopeType,
    department_names: scopeType === "departments" ? departmentNames : null,
  }
  const res = await authedFetch("/identity/admin/data-scopes", {
    method: "POST",
    body: JSON.stringify(body),
  })
  const result = await handleResponse(res)
  revalidatePath("/system/user-roles")
  return result
}

/** 删除数据范围配置（恢复默认：本部门+子部门） */
export async function deleteDataScope(ruleId: string) {
  const res = await authedFetch(`/identity/admin/data-scopes/${ruleId}`, {
    method: "DELETE",
  })
  const result = await handleResponse(res)
  revalidatePath("/system/roles")
  revalidatePath("/system/user-roles")
  return result
}

// ── 权限验证台 ──────────────────────────────────────────────────────

// 基于 generated schema 的 ViewModel：后端 openapi.json 对
// permission-preview / permission-simulate 的 200 响应未声明具体结构
// （响应 schema 为空 {}），故按后端实际返回定义以下前端视图类型。

export interface PermissionPreviewRoleItem {
  id: string
  name: string
  code: string
  description?: string | null
  is_system: boolean
  permissions: string[]
  /** 角色来源：manual=手动绑定 / department=部门匹配 */
  source: "manual" | "department"
  is_super_admin?: boolean
}

/** 权限预览中的可见菜单（扁平项，与后端 MenuResponse 结构一致） */
export interface PermissionPreviewMenu {
  id: string
  key?: string | null
  parent_id?: string | null
  name: string
  type: string
  permission_code?: string | null
  route_path?: string | null
  component_path?: string | null
  icon?: string | null
  sort_order: number
  status: string
}

/** 权限预览返回 data（账号权限快照） */
export interface PermissionPreviewData {
  user_id: string
  name: string
  roles: PermissionPreviewRoleItem[]
  permissions: string[]
  menus: PermissionPreviewMenu[]
  data_scope: {
    is_all: boolean
    department_names: string[]
  }
  /** 快照解析时刻（UTC ISO 字符串） */
  effective_at: string
}

/** 接口准入模拟返回 data */
export interface PermissionSimulateData {
  allowed: boolean
  reason: string
  required: string | null
  note: string | null
  /** HR 路径且传 department 时的可见部门参考提示（仅展示，不影响判定） */
  dept_scope_hint?: string | null
}

/** 账号权限预览（严格只读快照：角色来源/权限/菜单/数据范围） */
export async function previewUserPermission(
  userId: string,
): Promise<PermissionPreviewData> {
  const res = await authedFetch(
    `/identity/admin/users/${userId}/permission-preview`
  )
  const result = await handleResponse(res)
  return result as PermissionPreviewData
}

/** 接口准入模拟（只读判定，不真实执行请求） */
export async function simulatePermission(
  input: PermissionSimulateRequest,
): Promise<PermissionSimulateData> {
  const res = await authedFetch("/identity/admin/permission-simulate", {
    method: "POST",
    body: JSON.stringify(input),
  })
  const result = await handleResponse(res)
  return result as PermissionSimulateData
}

/** 导出权限清单 CSV（UTF-8 带 BOM），返回文件名与文本内容供前端触发下载 */
export async function exportPermissions(): Promise<{
  filename: string
  content: string
}> {
  const res = await authedFetch("/identity/admin/permissions/export")
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
  const content = await res.text()
  const disposition = res.headers.get("Content-Disposition") ?? ""
  const match = /filename="?([^";]+)"?/.exec(disposition)
  return { filename: match?.[1] ?? "permissions.csv", content }
}