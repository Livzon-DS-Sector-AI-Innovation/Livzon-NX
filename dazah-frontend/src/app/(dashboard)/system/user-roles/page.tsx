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
      <h1 className="text-xl font-semibold text-[var(--color-charcoal)]">用户角色</h1>
      <UserRoleManager initialRoles={roles} initialDepartments={departments} />
    </div>
  )
}
