import { OotLedgerPage } from '@/components/quality'
import { QualityQueryProvider } from '@/components/quality'

export default function Page() {
  return (
    <QualityQueryProvider>
      <OotLedgerPage />
    </QualityQueryProvider>
  )
}
