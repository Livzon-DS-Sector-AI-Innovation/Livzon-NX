import { serverFetchDepartments, serverFetchRoles } from "@/lib/api/server/admin"
import { RoleManager } from "@/components/system/RoleManager"

export const dynamic = "force-dynamic"

export default async function RolesPage() {
  const [roles, departments] = await Promise.all([
    serverFetchRoles(),
    serverFetchDepartments(),
  ])

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-[var(--color-charcoal)]">角色管理</h1>
        <p className="text-sm text-[var(--color-stone)] mt-1">
          创建、编辑角色，并按菜单页面配置访问、查询、操作、高风险业务动作与数据范围。
        </p>
      </div>
      <RoleManager
        initialRoles={roles}
        initialDepartments={departments}
      />
    </div>
  )
}
