import { beforeEach, expect, it, vi } from "vitest"
import type { RolePagePermissionsOut } from "@/actions/admin"
import type { DepartmentItem, RoleItem } from "@/lib/api/server/admin"
import RolePagePermissionsPage from "./page"

const mocks = vi.hoisted(() => ({
  roles: vi.fn(), departments: vi.fn(), grants: vi.fn(),
}))
vi.mock("@/lib/api/server/admin", () => ({ serverFetchRoles: mocks.roles }))
vi.mock("@/actions/users", () => ({ getPermissionDepartments: mocks.departments }))
vi.mock("@/actions/admin", () => ({ getRolePagePermissions: mocks.grants }))
vi.mock("@/components/system/RolePagePermissionsWorkbench", () => ({ RolePagePermissionsRoute: () => null }))
vi.mock("next/navigation", () => ({ notFound: () => { throw new Error("NOT_FOUND") } }))

const role: RoleItem = { id: "role-a", code: "role_a", name: "测试角色", is_system: false, permissions: [] }
const grants: RolePagePermissionsOut = { role_id: role.id, grant_version: 7, grants: [], definitions: [] }
const routeProps = {
  params: Promise.resolve({ roleId: role.id }),
  searchParams: Promise.resolve({ from: "health", page: "hr:profile" }),
}

beforeEach(() => {
  vi.resetAllMocks()
  mocks.roles.mockResolvedValue([role])
  mocks.departments.mockResolvedValue([])
  mocks.grants.mockResolvedValue(grants)
})

it("starts the three reads together and supplies the grants to the first render", async () => {
  const roles = Promise.withResolvers<RoleItem[]>()
  const departments = Promise.withResolvers<DepartmentItem[]>()
  const permissions = Promise.withResolvers<RolePagePermissionsOut>()
  mocks.roles.mockReturnValue(roles.promise)
  mocks.departments.mockReturnValue(departments.promise)
  mocks.grants.mockReturnValue(permissions.promise)

  const page = RolePagePermissionsPage(routeProps)
  await vi.waitFor(() => {
    expect(mocks.roles).toHaveBeenCalledOnce()
    expect(mocks.departments).toHaveBeenCalledOnce()
    expect(mocks.grants).toHaveBeenCalledWith(role.id)
  })
  permissions.resolve(grants)
  departments.resolve([])
  roles.resolve([role])
  expect((await page).props).toEqual(expect.objectContaining({
    role, origin: "health", initialPageKey: "hr:profile", initialLoad: { ok: true, data: grants },
  }))
})

it("passes a permission load failure to the workbench retry state", async () => {
  mocks.grants.mockRejectedValue(new Error("授权暂时不可用"))
  expect((await RolePagePermissionsPage(routeProps)).props.initialLoad)
    .toEqual({ ok: false, message: "授权暂时不可用" })
})

it("rejects opening a protected role even when a grant response is available", async () => {
  mocks.roles.mockResolvedValue([{ ...role, code: "super_admin" }])
  await expect(RolePagePermissionsPage(routeProps)).rejects.toThrow("NOT_FOUND")
})
