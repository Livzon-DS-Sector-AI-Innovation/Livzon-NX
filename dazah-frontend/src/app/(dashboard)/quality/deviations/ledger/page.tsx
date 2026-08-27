import { DeviationPage, QualityQueryProvider } from '@/components/quality'

export default function DeviationLedgerPage() {
  return (
    <QualityQueryProvider>
      <DeviationPage />
    </QualityQueryProvider>
  )
}
