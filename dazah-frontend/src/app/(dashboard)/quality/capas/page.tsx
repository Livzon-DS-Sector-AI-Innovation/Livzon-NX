import { CapaDashboardPage, ErrorBoundary, QualityQueryProvider } from '@/components/quality'

export default function CapasPage() {
  return (
    <ErrorBoundary>
      <QualityQueryProvider>
        <CapaDashboardPage />
      </QualityQueryProvider>
    </ErrorBoundary>
  )
}
