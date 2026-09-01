import { QualityQueryProvider } from '@/components/quality'
import { InspectionFeishuTable } from '@/components/quality/inspection'

export const dynamic = 'force-dynamic'

export default function EquipmentPage() {
  return (
    <QualityQueryProvider>
      <InspectionFeishuTable
        title="设备数据管理"
        listApi="/api/v1/quality/instruments/equipment"
        pullApi="/api/v1/quality/instruments/equipment/pull"
        entityCode="qc_instr_equipment"
        editable
        filters={[
          { key: '设备状态', label: '设备状态' },
          { key: '设备类型', label: '设备类型' },
        ]}
      />
    </QualityQueryProvider>
  )
}
