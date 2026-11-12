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
        <h1 className="text-xl font-semibold text-[var(--color-charcoal)]">角色映射</h1>
        <p className="text-sm text-[var(--color-stone)] mt-1">
          搜索用户或按部门查询，为所选用户批量分配角色。
        </p>
      </div>
      <DeptRoleMapper initialRules={rules} initialRoles={roles} initialDepartments={departments} />
    </div>
  )
}
