import { QualityQueryProvider } from '@/components/quality/QualityQueryProvider'
import { WaterInspectionPage } from '@/components/quality/inspection/WaterInspectionPage'

export const dynamic = 'force-dynamic'

export default function FinishedWaterPage() {
  return (
    <QualityQueryProvider>
      <WaterInspectionPage />
    </QualityQueryProvider>
  )
}
