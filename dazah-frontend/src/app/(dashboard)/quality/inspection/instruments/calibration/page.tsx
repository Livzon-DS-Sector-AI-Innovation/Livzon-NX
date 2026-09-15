import { QualityQueryProvider } from '@/components/quality'
import { InspectionFeishuTable } from '@/components/quality/inspection'

export const dynamic = 'force-dynamic'

export default function InstrCalibrationPage() {
  return (
    <QualityQueryProvider>
      <InspectionFeishuTable
        title="内校汇总"
        listApi="/api/v1/quality/instruments/calibration"
        pullApi="/api/v1/quality/instruments/calibration/pull"
        entityCode="qc_instr_calibration"
        editable
        editablePersonFields
        enableTextPreview
        enableAttachmentPreview
        showLastSyncTime
      />
    </QualityQueryProvider>
  )
}