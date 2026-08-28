/**
 * 权限管理 - 浏览器端 GET API（只读）
 * 使用相对路径 /api/v1/...（自动代理到后端）
 */
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

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    if (res.status === 401) {
      // 401 拦截：清除 cookie + 跳转登录页
      window.location.href = "/login"
      throw new Error("未登录或登录已过期")
    }
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

export async function fetchPermissions(): Promise<PermissionItem[]> {
  const res = await fetch("/api/v1/identity/admin/permissions", { cache: "no-store" })
  return handleResponse<PermissionItem[]>(res)
}

export async function fetchRoles(): Promise<RoleItem[]> {
  const res = await fetch("/api/v1/identity/admin/roles", { cache: "no-store" })
  return handleResponse<RoleItem[]>(res)
}

export async function fetchAdminUsers(): Promise<{ items: AdminUserItem[]; total: number }> {
  const res = await fetch("/api/v1/identity/admin/users?limit=500", { cache: "no-store" })
  return handleResponse<{ items: AdminUserItem[]; total: number }>(res)
}

export async function fetchDeptRules(): Promise<DeptRuleItem[]> {
  const res = await fetch("/api/v1/identity/admin/dept-rules", { cache: "no-store" })
  return handleResponse<DeptRuleItem[]>(res)
}

/** 角色已绑定的菜单 id 列表（角色页菜单权限树回显） */
export async function fetchRoleMenus(roleId: string): Promise<string[]> {
  const res = await fetch(`/api/v1/identity/admin/roles/${roleId}/menus`, {
    cache: "no-store",
  })
  return handleResponse<{ role_id: string; menu_ids: string[] }>(res).then(
    (data) => data.menu_ids ?? []
  )
}

/** 数据范围配置（角色/用户可见部门） */
export interface DataScopeRuleItem {
  id: string
  role_id?: string | null
  user_id?: string | null
  scope_type: "all" | "departments"
  department_names: string[]
}

/** 数据范围配置列表（前端回显按 role_id/user_id 匹配） */
export async function fetchDataScopes(): Promise<DataScopeRuleItem[]> {
  const res = await fetch("/api/v1/identity/admin/data-scopes", { cache: "no-store" })
  return handleResponse<DataScopeRuleItem[]>(res)
}
