import { Suspense } from 'react'
import { FinishedProductAnomalyTablePage, QualityQueryProvider } from '@/components/quality'

export default function QualityAnomalyReportLedgerPage() {
  return (
    <QualityQueryProvider>
      <Suspense fallback={null}>
        <FinishedProductAnomalyTablePage />
      </Suspense>
    </QualityQueryProvider>
  )
}
