import { QualityQueryProvider } from '@/components/quality/QualityQueryProvider'
import { MpaInspectionPage } from '@/components/quality/inspection/MpaInspectionPage'

export const dynamic = 'force-dynamic'

export default function FinishedMpaPage() {
  return (
    <QualityQueryProvider>
      <MpaInspectionPage />
    </QualityQueryProvider>
  )
}
