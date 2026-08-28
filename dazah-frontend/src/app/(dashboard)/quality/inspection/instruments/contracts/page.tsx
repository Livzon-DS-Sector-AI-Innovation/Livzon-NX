import { QualityQueryProvider } from '@/components/quality'
import { InspectionFeishuTable } from '@/components/quality/inspection'

export const dynamic = 'force-dynamic'

export default function InstrContractsPage() {
  return (
    <QualityQueryProvider>
      <InspectionFeishuTable
        title="设备维保合同"
        listApi="/api/v1/quality/instruments/contracts"
        pullApi="/api/v1/quality/instruments/contracts/pull"
      />
    </QualityQueryProvider>
  )
}
