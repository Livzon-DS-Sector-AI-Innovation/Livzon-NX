import { QualityQueryProvider } from '@/components/quality/QualityQueryProvider'
import { LftInspectionPage } from '@/components/quality/inspection/LftInspectionPage'

export const dynamic = 'force-dynamic'

export default function FinishedLftPage() {
  return (
    <QualityQueryProvider>
      <LftInspectionPage />
    </QualityQueryProvider>
  )
}
