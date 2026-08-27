import { CapaPage, ErrorBoundary, QualityQueryProvider } from '@/components/quality'

export default function CapaLedgerPage() {
  return (
    <ErrorBoundary>
      <QualityQueryProvider>
        <CapaPage />
      </QualityQueryProvider>
    </ErrorBoundary>
  )
}
