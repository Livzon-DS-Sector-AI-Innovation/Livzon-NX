import { QualityQueryProvider } from '@/components/quality'
import { InspectionFeishuTable } from '@/components/quality/inspection'

export const dynamic = 'force-dynamic'

export default function InstrRepairPage() {
  return (
    <QualityQueryProvider>
      <InspectionFeishuTable
        title="设备维修记录"
        listApi="/api/v1/quality/instruments/repair"
        pullApi="/api/v1/quality/instruments/repair/pull"
      />
    </QualityQueryProvider>
  )
}
