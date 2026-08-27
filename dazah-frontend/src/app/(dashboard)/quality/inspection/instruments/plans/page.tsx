import { QualityQueryProvider } from '@/components/quality'
import { InspectionFeishuTable } from '@/components/quality/inspection'

export const dynamic = 'force-dynamic'

export default function InstrPlansPage() {
  return (
    <QualityQueryProvider>
      <InspectionFeishuTable
        title="设备维护保养方案"
        listApi="/api/v1/quality/instruments/plans"
        pullApi="/api/v1/quality/instruments/plans/pull"
      />
    </QualityQueryProvider>
  )
}
