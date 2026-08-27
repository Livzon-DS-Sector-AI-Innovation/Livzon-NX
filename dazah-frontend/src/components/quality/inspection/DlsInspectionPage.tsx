'use client'

import { FinishedSubtablePage } from './FinishedSubtablePage'
import { DlsTrendDashboard } from './DlsTrendDashboard'

export function DlsInspectionPage() {
  return (
    <FinishedSubtablePage
      title="多拉菌素"
      productGroup="dls"
      renderDashboardContent={({ selectedEntityCode }) => (
        <DlsTrendDashboard entityCode={selectedEntityCode} />
      )}
    />
  )
}
