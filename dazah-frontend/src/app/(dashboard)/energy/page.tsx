import { EnergyOverview, EnergyQueryProvider } from '@/components/energy'

export const dynamic = 'force-dynamic'

export default function EnergyPage() {
  return (
    <EnergyQueryProvider>
      <EnergyOverview />
    </EnergyQueryProvider>
  )
}
