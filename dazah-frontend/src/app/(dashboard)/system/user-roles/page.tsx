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
          为用户分配角色，模块入口随有效页面权限自动生效。
        </p>
      </div>
      <UserRoleManager initialRoles={roles} initialDepartments={departments} />
    </div>
  )
}
