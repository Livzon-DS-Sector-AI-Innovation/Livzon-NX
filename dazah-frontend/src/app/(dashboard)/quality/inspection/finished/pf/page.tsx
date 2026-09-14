import { PfInspectionPage } from '@/components/quality/inspection/PfInspectionPage'
import { QualityQueryProvider } from '@/components/quality/QualityQueryProvider'

export const dynamic = 'force-dynamic'

export default function FinishedPfPage() {
  return (
    <QualityQueryProvider>
      <PfInspectionPage />
    </QualityQueryProvider>
  )
}
