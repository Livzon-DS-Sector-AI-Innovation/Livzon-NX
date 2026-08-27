'use client'

import { FinishedSubtablePage } from './FinishedSubtablePage'
import { LftTrendDashboard } from './LftTrendDashboard'

export function LftInspectionPage() {
  return (
    <FinishedSubtablePage
      title="洛伐他汀"
      productGroup="lft"
      renderDashboardContent={({ selectedEntityCode }) => (
        <LftTrendDashboard entityCode={selectedEntityCode} />
      )}
    />
  )
}
