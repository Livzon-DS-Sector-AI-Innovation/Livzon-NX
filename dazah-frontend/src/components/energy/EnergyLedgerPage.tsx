import { Suspense } from 'react'
import { EnergyQueryProvider } from './EnergyQueryProvider'
import { EnergyWorkspace, type EnergyMode } from './EnergyWorkspace'

export default function EnergyLedgerPage({ mode }: { mode: EnergyMode }) {
  return <EnergyQueryProvider><Suspense fallback={<p role="status">正在加载能源工作台…</p>}><EnergyWorkspace mode={mode} /></Suspense></EnergyQueryProvider>
}
