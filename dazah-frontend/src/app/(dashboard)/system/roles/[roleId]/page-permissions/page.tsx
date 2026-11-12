import { notFound } from "next/navigation"
import { RolePagePermissionsRoute } from "@/components/system/RolePagePermissionsWorkbench"
import { serverFetchRoles } from "@/lib/api/server/admin"
import { getPermissionDepartments } from "@/actions/users"
import { getRolePagePermissions } from "@/actions/admin"

export default async function RolePagePermissionsPage({ params, searchParams }: {
  params: Promise<{ roleId: string }>
  searchParams: Promise<{ from?: string | string[]; page?: string | string[] }>
}) {
  const [{ roleId }, query] = await Promise.all([params, searchParams])
  const [availableRoles, departments, initialLoad] = await Promise.all([
    serverFetchRoles(),
    getPermissionDepartments(),
    getRolePagePermissions(roleId).then(
      (data) => ({ ok: true as const, data }),
      (error: unknown) => ({
        ok: false as const,
        message: error instanceof Error ? error.message : "加载角色页面权限失败",
      }),
    ),
  ])
  const roles = availableRoles.filter(({ code }) => code !== "super_admin" && code !== "ordinary_admin")
  const role = roles.find(({ id }) => id === roleId)
  if (!role) notFound()
  const origin = query.from === "settings" || query.from === "health" ? query.from : "roles"

  return <RolePagePermissionsRoute role={role} roles={roles} departments={departments} origin={origin} initialLoad={initialLoad}
    initialPageKey={typeof query.page === "string" ? query.page : undefined} />
}
