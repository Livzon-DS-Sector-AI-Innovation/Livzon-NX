import { CapaPlanTrackPage, ErrorBoundary, QualityQueryProvider } from '@/components/quality'

export default function CapaPlansPage() {
  return (
    <ErrorBoundary>
      <QualityQueryProvider>
        <CapaPlanTrackPage />
      </QualityQueryProvider>
    </ErrorBoundary>
  )
}
