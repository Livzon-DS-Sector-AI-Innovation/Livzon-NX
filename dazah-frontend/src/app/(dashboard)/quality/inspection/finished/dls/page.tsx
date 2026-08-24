import { QualityQueryProvider } from '@/components/quality/QualityQueryProvider'
import { DlsInspectionPage } from '@/components/quality/inspection/DlsInspectionPage'

export const dynamic = 'force-dynamic'

export default function FinishedDlsPage() {
  return (
    <QualityQueryProvider>
      <DlsInspectionPage />
    </QualityQueryProvider>
  )
}
