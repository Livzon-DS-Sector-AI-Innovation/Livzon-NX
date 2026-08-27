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
          管理员可查看任意账号的生效权限并模拟接口访问，结果与真实执行一致。
        </p>
      </div>
      <PermissionVerification users={users} />
    </div>
  )
}
