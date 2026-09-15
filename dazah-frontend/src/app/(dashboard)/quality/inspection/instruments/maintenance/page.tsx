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
        entityCode="qc_instr_maintenance"
        editable
        editablePersonFields
        enableAttachmentPreview
        showLastSyncTime
        hiddenFields={['父记录']}
        filters={[
          { key: '是否完成', label: '是否完成' },
          { key: '维保类型', label: '维保类型' },
        ]}
      />
    </QualityQueryProvider>
  )
}