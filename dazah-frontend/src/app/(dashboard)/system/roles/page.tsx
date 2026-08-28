import { serverFetchDepartments, serverFetchMenus, serverFetchPermissions, serverFetchRoles } from "@/lib/api/server/admin"
import { RoleManager } from "@/components/system/RoleManager"

export const dynamic = "force-dynamic"

export default async function RolesPage() {
  const [roles, permissions, menus, departments] = await Promise.all([
    serverFetchRoles(),
    serverFetchPermissions(),
    serverFetchMenus(),
    serverFetchDepartments(),
  ])

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-[var(--color-charcoal)]">角色管理</h1>
        <p className="text-sm text-[var(--color-stone)] mt-1">
          创建、编辑、删除角色，并为角色绑定模块权限点（读/写）、菜单权限（菜单/按钮）与可见部门（数据范围）。
        </p>
      </div>
      <RoleManager
        initialRoles={roles}
        initialPermissions={permissions}
        initialMenus={menus}
        initialDepartments={departments}
      />
    </div>
  )
}