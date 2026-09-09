import { serverFetchDeptRules, serverFetchDepartments, serverFetchRoles } from "@/lib/api/server/admin"
import { DeptRoleMapper } from "@/components/system/DeptRoleMapper"

export const dynamic = "force-dynamic"

export default async function DeptRolesPage() {
  const [rules, roles, departments] = await Promise.all([
    serverFetchDeptRules(),
    serverFetchRoles(),
    serverFetchDepartments(),
  ])

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-[var(--color-charcoal)]">部门角色映射</h1>
        <p className="text-sm text-[var(--color-stone)] mt-1">
          按部门查询用户，筛选并勾选需要应用角色的人员。
        </p>
      </div>
      <DeptRoleMapper initialRules={rules} initialRoles={roles} initialDepartments={departments} />
    </div>
  )
}
