import { ValidationLedgerPage } from '@/components/quality'

export default function QualityOtherValidationsPage() {
  return (
    <ValidationLedgerPage
      mode="child"
      validationType="other_validation"
      title="其他验证"
      description="展示验证主计划自动同步的其他验证执行记录，并维护执行跟踪信息。"
    />
  )
}
