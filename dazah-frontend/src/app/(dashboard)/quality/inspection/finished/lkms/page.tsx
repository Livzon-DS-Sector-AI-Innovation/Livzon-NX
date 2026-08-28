import { QualityQueryProvider } from '@/components/quality/QualityQueryProvider'
import { LkmsInspectionPage } from '@/components/quality/inspection/LkmsInspectionPage'

export const dynamic = 'force-dynamic'

export default function FinishedLkmsPage() {
  return (
    <QualityQueryProvider>
      <LkmsInspectionPage />
    </QualityQueryProvider>
  )
}
