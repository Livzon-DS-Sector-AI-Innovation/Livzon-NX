import { QualityQueryProvider } from '@/components/quality'
import { InspectionFeishuTable } from '@/components/quality/inspection'

export const dynamic = 'force-dynamic'

export default function InstrPlansPage() {
  return (
    <QualityQueryProvider>
      <InspectionFeishuTable
        title="QC检测仪器维护保养周期表"
        listApi="/api/v1/quality/instruments/plans"
        pullApi="/api/v1/quality/instruments/plans/pull"
        entityCode="qc_instr_plans"
        editable
        enableTextPreview
        showLastSyncTime
      />
    </QualityQueryProvider>
  )
}