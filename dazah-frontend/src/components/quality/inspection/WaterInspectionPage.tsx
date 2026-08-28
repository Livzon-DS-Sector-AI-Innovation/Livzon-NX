'use client'

import { FinishedSubtablePage } from './FinishedSubtablePage'
import { WaterTrendDashboard } from './WaterTrendDashboard'

export function WaterInspectionPage() {
  return (
    <FinishedSubtablePage
      title="纯化水等"
      productGroup="water"
      renderDashboardContent={({ selectedEntityCode }) => (
        <WaterTrendDashboard entityCode={selectedEntityCode} />
      )}
    />
  )
}
