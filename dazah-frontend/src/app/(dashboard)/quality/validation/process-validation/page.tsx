import { ValidationLedgerPage } from '@/components/quality'

export default function QualityProcessValidationPage() {
  return (
    <ValidationLedgerPage
      mode="child"
      validationType="process_validation"
      title="工艺验证"
      description="展示验证主计划自动同步的工艺验证执行记录，并维护执行跟踪信息。"
    />
  )
}
