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
        entityCode="qc_instr_repair"
        editable
        editablePersonFields
        enableAttachmentPreview
        showLastSyncTime
        /* 新增只走飞书共享表单（质量设置-飞书设置可配链接），不走本地弹窗 */
        createFormOnly
        filters={[{ key: '维修状态', label: '维修状态' }]}
      />
    </QualityQueryProvider>
  )
}