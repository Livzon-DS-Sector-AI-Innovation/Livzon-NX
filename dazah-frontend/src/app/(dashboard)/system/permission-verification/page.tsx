import { serverFetchAdminUsers } from "@/lib/api/server/admin"
import { PermissionVerification } from "@/components/system"

export const dynamic = "force-dynamic"

export default async function PermissionVerificationPage() {
  const users = await serverFetchAdminUsers()

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-[var(--color-charcoal)]">权限验证台</h1>
        <p className="text-sm text-[var(--color-stone)] mt-1">
          按账号、菜单页面和中文业务动作验证生效权限，无需理解接口路径或请求方法。
        </p>
      </div>
      <PermissionVerification users={users} />
    </div>
  )
}
