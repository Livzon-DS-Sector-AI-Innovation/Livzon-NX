import { PermissionVerification } from "@/components/system"

export const dynamic = "force-dynamic"

export default function PermissionVerificationPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-[var(--color-charcoal)]">权限接入检查</h1>
      <PermissionVerification />
    </div>
  )
}
