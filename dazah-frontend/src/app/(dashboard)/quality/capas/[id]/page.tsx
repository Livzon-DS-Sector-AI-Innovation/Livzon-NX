import { CapaDetail, ErrorBoundary, QualityQueryProvider } from '@/components/quality'

export default function CapaDetailPage() {
  return (
    <ErrorBoundary>
      <QualityQueryProvider>
        <CapaDetail />
      </QualityQueryProvider>
    </ErrorBoundary>
  )
}
