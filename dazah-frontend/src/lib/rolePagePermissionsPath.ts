export type PermissionWorkbenchOrigin = "roles" | "settings" | "health"

export function rolePagePermissionsPath(roleId: string, origin: PermissionWorkbenchOrigin = "roles", pageKey?: string) {
  const query = new URLSearchParams()
  if (origin !== "roles") query.set("from", origin)
  if (pageKey) query.set("page", pageKey)
  const search = query.toString()
  return `/system/roles/${encodeURIComponent(roleId)}/page-permissions${search ? `?${search}` : ""}`
}
