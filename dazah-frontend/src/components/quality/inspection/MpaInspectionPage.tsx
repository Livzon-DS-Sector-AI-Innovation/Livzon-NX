'use client'

import { FinishedSubtablePage } from './FinishedSubtablePage'
import { MpaTrendDashboard } from './MpaTrendDashboard'

export function MpaInspectionPage() {
  return (
    <FinishedSubtablePage
      title="霉酚酸"
      productGroup="mpa"
      renderDashboardContent={({ selectedEntityCode }) => (
        <MpaTrendDashboard entityCode={selectedEntityCode} />
      )}
    />
  )
}
