import { getNonConformingEvents, getShiftHandovers, getShiftLogs } from '@/actions/production'
import { ShiftOperationsClient } from '@/components/production/ShiftOperationsClient'

export default async function ShiftLogPage() {
  const [events, logs, handovers] = await Promise.all([getNonConformingEvents(), getShiftLogs(), getShiftHandovers()])
  return <ShiftOperationsClient initialEvents={events.data || []} initialLogs={logs.data || []} initialHandovers={handovers.data || []} />
}
