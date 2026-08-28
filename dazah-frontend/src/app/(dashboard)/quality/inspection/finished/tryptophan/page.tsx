import { QualityQueryProvider } from '@/components/quality/QualityQueryProvider'
import { TryptophanInspectionPage } from '@/components/quality/inspection/TryptophanInspectionPage'

export const dynamic = 'force-dynamic'

export default function FinishedTryptophanPage() {
  return (
    <QualityQueryProvider>
      <TryptophanInspectionPage />
    </QualityQueryProvider>
  )
}
