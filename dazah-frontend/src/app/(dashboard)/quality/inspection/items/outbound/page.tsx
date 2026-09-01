import { QualityQueryProvider } from '@/components/quality'
import { InspectionFeishuTable } from '@/components/quality/inspection'

export const dynamic = 'force-dynamic'

export default function ItemsOutboundPage() {
  return (
    <QualityQueryProvider>
      <InspectionFeishuTable
        title="领用明细"
        listApi="/api/v1/quality/items/outbound"
        pullApi="/api/v1/quality/items/outbound/pull"
        entityCode="qc_items_outbound"
        editable
      />
    </QualityQueryProvider>
  )
}
