import { QualityQueryProvider } from '@/components/quality'
import { InspectionFeishuTable } from '@/components/quality/inspection'

export const dynamic = 'force-dynamic'

export default function InstrMaintenancePage() {
  return (
    <QualityQueryProvider>
      <InspectionFeishuTable
        title="设备维护保养记录"
        listApi="/api/v1/quality/instruments/maintenance"
        pullApi="/api/v1/quality/instruments/maintenance/pull"
      />
    </QualityQueryProvider>
  )
}
