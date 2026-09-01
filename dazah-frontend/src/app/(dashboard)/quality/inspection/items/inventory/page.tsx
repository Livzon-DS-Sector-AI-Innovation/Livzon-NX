import { QualityQueryProvider } from '@/components/quality'
import { InspectionFeishuTable } from '@/components/quality/inspection'

export const dynamic = 'force-dynamic'

export default function ItemsInventoryPage() {
  return (
    <QualityQueryProvider>
      <InspectionFeishuTable
        title="关键物资库存"
        listApi="/api/v1/quality/items/inventory"
        pullApi="/api/v1/quality/items/inventory/pull"
        entityCode="qc_items_inventory"
        editable
        filters={[
          { key: '存放位置', label: '存放位置', type: 'select', options: [
            { label: '物资储存室', value: '物资储存室' },
            { label: '资料室', value: '资料室' },
            { label: '经理办公室', value: '经理办公室' },
          ]},
          { key: '库存报警', label: '库存报警', type: 'select', options: [
            { label: '正常', value: '正常' },
            { label: '库存不足', value: '库存不足' },
          ]},
        ]}
      />
    </QualityQueryProvider>
  )
}
