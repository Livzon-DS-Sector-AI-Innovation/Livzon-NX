import { QualityQueryProvider } from '@/components/quality'
import { ItemsDashboard } from '@/components/quality/inspection/ItemsDashboard'

export const dynamic = 'force-dynamic'

export default function InspectionItemsPage() {
  return (
    <QualityQueryProvider>
      <ItemsDashboard />
    </QualityQueryProvider>
  )
}
