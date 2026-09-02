import { QualityQueryProvider } from '@/components/quality'
import { InspectionFeishuTable } from '@/components/quality/inspection'

export const dynamic = 'force-dynamic'

export default function ItemsInboundPage() {
  return (
    <QualityQueryProvider>
      <InspectionFeishuTable
        title="入库明细"
        listApi="/api/v1/quality/items/inbound"
        pullApi="/api/v1/quality/items/inbound/pull"
        entityCode="qc_items_inbound"
        editable
      />
    </QualityQueryProvider>
  )
}
