import { QualityQueryProvider } from '@/components/quality'
import { ItemsInventoryTable } from '@/components/quality/inspection/ItemsInventoryTable'

export const dynamic = 'force-dynamic'

export default function ItemsInventoryPage() {
  return (
    <QualityQueryProvider>
      <ItemsInventoryTable />
    </QualityQueryProvider>
  )
}
