import { serverFetchDepartments, serverFetchRoles } from "@/lib/api/server/admin"
import { UserRoleManager } from "@/components/system/UserRoleManager"

export const dynamic = "force-dynamic"

export default async function UserRolesPage() {
  const [roles, departments] = await Promise.all([
    serverFetchRoles(),
    serverFetchDepartments(),
  ])

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-[var(--color-charcoal)]">用户角色</h1>
        <p className="text-sm text-[var(--color-stone)] mt-1">
          为用户手动分配角色与可见部门（部门映射角色由组织架构自动推导，此处只展示）。
        </p>
      </div>
      <UserRoleManager initialRoles={roles} initialDepartments={departments} />
    </div>
  )
}