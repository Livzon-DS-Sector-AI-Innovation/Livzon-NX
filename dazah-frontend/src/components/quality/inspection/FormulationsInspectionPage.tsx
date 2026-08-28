'use client'

import { FinishedSubtablePage } from './FinishedSubtablePage'
import { FormulationsTrendDashboard } from './FormulationsTrendDashboard'

export function FormulationsInspectionPage() {
  return (
    <FinishedSubtablePage
      title="MSD预混剂"
      productGroup="formulations"
      renderDashboardContent={({ selectedEntityCode }) => (
        <FormulationsTrendDashboard entityCode={selectedEntityCode} />
      )}
    />
  )
}
