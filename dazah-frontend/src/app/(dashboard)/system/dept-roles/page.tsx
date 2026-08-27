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
          配置部门 → 角色的自动映射规则（成员入职后按部门自动获得角色）。
        </p>
      </div>
      <DeptRoleMapper initialRules={rules} initialRoles={roles} initialDepartments={departments} />
    </div>
  )
}