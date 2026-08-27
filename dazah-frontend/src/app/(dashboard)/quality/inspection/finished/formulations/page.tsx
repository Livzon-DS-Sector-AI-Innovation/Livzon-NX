import { QualityQueryProvider } from '@/components/quality/QualityQueryProvider'
import { FormulationsInspectionPage } from '@/components/quality/inspection/FormulationsInspectionPage'

export const dynamic = 'force-dynamic'

export default function FinishedFormulationsPage() {
  return (
    <QualityQueryProvider>
      <FormulationsInspectionPage />
    </QualityQueryProvider>
  )
}
