import { ValidationLedgerPage } from '@/components/quality'

export default function QualityEquipmentQualificationPage() {
  return (
    <ValidationLedgerPage
      mode="child"
      validationType="equipment_qualification"
      title="设备确认"
      description="展示验证主计划自动同步的设备确认执行记录，并维护执行跟踪信息。"
    />
  )
}
