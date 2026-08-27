'use client'

import { FinishedSubtablePage } from './FinishedSubtablePage'
import { BbasTrendDashboard } from './BbasTrendDashboard'

export function BbasInspectionPage() {
  return (
    <FinishedSubtablePage
      title="L-苯丙氨酸"
      productGroup="bbas"
      renderDashboardContent={({ selectedEntityCode }) => (
        <BbasTrendDashboard entityCode={selectedEntityCode} />
      )}
    />
  )
}
