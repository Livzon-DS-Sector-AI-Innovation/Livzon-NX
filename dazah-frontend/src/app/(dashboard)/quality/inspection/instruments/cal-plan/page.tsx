import { QualityQueryProvider } from '@/components/quality'
import { InspectionFeishuTable } from '@/components/quality/inspection'

export const dynamic = 'force-dynamic'

export default function InstrCalPlanPage() {
  return (
    <QualityQueryProvider>
      <InspectionFeishuTable
        title="内部校验计划"
        listApi="/api/v1/quality/instruments/cal-plan"
        pullApi="/api/v1/quality/instruments/cal-plan/pull"
        entityCode="qc_instr_cal_plan"
        editable
        editablePersonFields
        enableAttachmentPreview
        showLastSyncTime
        filters={[
          { key: '状态', label: '状态' },
          { key: '是否知晓', label: '是否知晓' },
        ]}
      />
    </QualityQueryProvider>
  )
}