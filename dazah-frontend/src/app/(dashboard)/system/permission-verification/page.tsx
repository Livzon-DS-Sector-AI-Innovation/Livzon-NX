import { PermissionVerification } from "@/components/system"

export const dynamic = "force-dynamic"

export default function PermissionVerificationPage() {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-[var(--color-charcoal)]">权限接入检查</h1>
        <p className="text-sm text-[var(--color-stone)] mt-1">
          自动检查各模块的权限接入完整性，并诊断当前授权条件和健康问题。
        </p>
      </div>
      <PermissionVerification />
    </div>
  )
}
