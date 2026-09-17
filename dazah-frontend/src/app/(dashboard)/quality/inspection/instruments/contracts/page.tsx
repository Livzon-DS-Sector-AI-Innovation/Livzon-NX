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
        entityCode="qc_instr_contracts"
        editable
        editablePersonFields
        enableAttachmentPreview
        showLastSyncTime
        /* 新增只走飞书共享表单（质量设置-飞书设置可配链接），不走本地弹窗 */
        createFormOnly
      />
    </QualityQueryProvider>
  )
}