import { QualityQueryProvider } from '@/components/quality/QualityQueryProvider'
import { BbasInspectionPage } from '@/components/quality/inspection/BbasInspectionPage'

export const dynamic = 'force-dynamic'

export default function FinishedBbasPage() {
  return (
    <QualityQueryProvider>
      <BbasInspectionPage />
    </QualityQueryProvider>
  )
}
