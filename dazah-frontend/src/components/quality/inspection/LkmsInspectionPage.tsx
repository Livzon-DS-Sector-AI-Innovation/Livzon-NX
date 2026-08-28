'use client'

import { FinishedSubtablePage } from './FinishedSubtablePage'
import { LkmsTrendDashboard } from './LkmsTrendDashboard'

export function LkmsInspectionPage() {
  return (
    <FinishedSubtablePage
      title="林可霉素"
      productGroup="lkms"
      renderDashboardContent={({ selectedEntityCode }) => (
        <LkmsTrendDashboard entityCode={selectedEntityCode} />
      )}
    />
  )
}
