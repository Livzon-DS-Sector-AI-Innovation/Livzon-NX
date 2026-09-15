import { QualityQueryProvider } from '@/components/quality'
import { InstrumentLedgerPage } from '@/components/quality/inspection'

export const dynamic = 'force-dynamic'

export default function EquipmentPage() {
  return (
    <QualityQueryProvider>
      <InstrumentLedgerPage />
    </QualityQueryProvider>
  )
}