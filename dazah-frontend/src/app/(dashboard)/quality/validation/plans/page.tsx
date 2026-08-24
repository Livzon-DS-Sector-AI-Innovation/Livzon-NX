import { ValidationLedgerPage } from '@/components/quality'
import { QualityQueryProvider } from '@/components/quality'

export default function QualityValidationPlansPage() {
  return (
    <QualityQueryProvider>
      <ValidationLedgerPage
        mode="master"
        title="验证主计划"
        description="对齐飞书年度总表，统一查看和维护全部验证记录，并按验证类别自动分流到各分类页面。"
      />
    </QualityQueryProvider>
  )
}
