import { EnergyMappingClient, EnergyQueryProvider } from '@/components/energy'

export const dynamic = 'force-dynamic'

export default async function EnergyMappingPage({ params }: { params: Promise<{ sheetId: string }> }) {
  const { sheetId } = await params
  return (
    <EnergyQueryProvider>
      <EnergyMappingClient sheetId={sheetId} />
    </EnergyQueryProvider>
  )
}
