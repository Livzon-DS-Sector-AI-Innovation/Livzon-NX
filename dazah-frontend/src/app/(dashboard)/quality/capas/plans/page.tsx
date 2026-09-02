import { Suspense } from 'react'
import { CapaPlanTrackPage, ErrorBoundary, QualityQueryProvider } from '@/components/quality'

export default function CapaPlansPage() {
  return (
    <ErrorBoundary>
      <Suspense fallback={null}>
        <QualityQueryProvider>
          <CapaPlanTrackPage />
        </QualityQueryProvider>
      </Suspense>
    </ErrorBoundary>
  )
}
