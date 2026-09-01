import { QualityQueryProvider } from '@/components/quality'
import { InspectionFeishuTable } from '@/components/quality/inspection'

export const dynamic = 'force-dynamic'

export default function InstrChangePage() {
  return (
    <QualityQueryProvider>
      <InspectionFeishuTable
        title="设备变更记录"
        listApi="/api/v1/quality/instruments/change"
        pullApi="/api/v1/quality/instruments/change/pull"
        entityCode="qc_instr_change"
        editable
      />
    </QualityQueryProvider>
  )
}
