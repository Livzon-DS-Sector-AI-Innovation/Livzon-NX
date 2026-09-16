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
        showLastSyncTime
        wrapColumns
        centerHeaders
        columnWidths={{
          仪器类别: '12%',
          维护周期: '6%',
          '周期（月）': '6%',
          仪器编号: '32%',
          维护内容: '32%',
        }}
      />
    </QualityQueryProvider>
  )
}