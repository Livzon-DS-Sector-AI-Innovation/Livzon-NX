import { ValidationLedgerPage } from '@/components/quality'

export default function QualityCleaningValidationPage() {
  return (
    <ValidationLedgerPage
      mode="child"
      validationType="cleaning_validation"
      title="清洁验证"
      description="展示验证主计划自动同步的清洁验证执行记录，并维护执行跟踪信息。"
    />
  )
}
