import { QualityQueryProvider } from '@/components/quality'
import { InspectionFeishuTable } from '@/components/quality/inspection'

export const dynamic = 'force-dynamic'

export default function InstrCalExternalPage() {
  return (
    <QualityQueryProvider>
      <InspectionFeishuTable
        title="外部校准、检定"
        listApi="/api/v1/quality/instruments/cal-external"
        pullApi="/api/v1/quality/instruments/cal-external/pull"
        entityCode="qc_instr_cal_external"
        editable
        enableAttachmentPreview
        enableCertificateCreate
        showLastSyncTime
      />
    </QualityQueryProvider>
  )
}