import { EnergyQueryProvider, EnergySyncRunsClient } from '@/components/energy'

export const dynamic = 'force-dynamic'

export default function EnergySyncRunsPage() {
  return (
    <EnergyQueryProvider>
      <EnergySyncRunsClient />
    </EnergyQueryProvider>
  )
}
