import { QualityQueryProvider } from '@/components/quality'
import { InstrumentsDashboard } from '@/components/quality/inspection'

export const dynamic = 'force-dynamic'

export default function InspectionInstrumentsPage() {
  return (
    <QualityQueryProvider>
      <InstrumentsDashboard />
    </QualityQueryProvider>
  )
}