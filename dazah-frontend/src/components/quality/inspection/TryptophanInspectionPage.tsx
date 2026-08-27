'use client'

import { FinishedSubtablePage } from './FinishedSubtablePage'
import { TryptophanTrendDashboard } from './TryptophanTrendDashboard'

export function TryptophanInspectionPage() {
  return (
    <FinishedSubtablePage
      title="色氨酸"
      productGroup="tryptophan"
      renderDashboardContent={({ selectedEntityCode }) => (
        <TryptophanTrendDashboard entityCode={selectedEntityCode} />
      )}
    />
  )
}
