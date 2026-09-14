import { PermissionVerification } from "@/components/system"

export const dynamic = "force-dynamic"

export default function PermissionVerificationPage() {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-[var(--color-charcoal)]">权限接入检查</h1>
        <p className="text-sm text-[var(--color-stone)] mt-1">
          查看各模块的权限接入详情与门禁结果。模块访问和页面权限配置保存后立即生效。
        </p>
      </div>
      <PermissionVerification />
    </div>
  )
}
