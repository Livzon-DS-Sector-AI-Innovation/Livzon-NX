import { QualityQueryProvider } from '@/components/quality'
import { InspectionFeishuTable } from '@/components/quality/inspection'

export const dynamic = 'force-dynamic'

export default function InstrAssetsPage() {
  return (
    <QualityQueryProvider>
      <InspectionFeishuTable
        title="固资台账"
        listApi="/api/v1/quality/instruments/assets"
        pullApi="/api/v1/quality/instruments/assets/pull"
        entityCode="qc_instr_assets"
        editable
      />
    </QualityQueryProvider>
  )
}
