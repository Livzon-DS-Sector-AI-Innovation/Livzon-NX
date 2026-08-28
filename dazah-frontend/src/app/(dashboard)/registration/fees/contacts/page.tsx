import { fetchInspectionContactsServer } from '@/lib/api/server/registration'
import { InspectionContactsPage } from '@/components/registration'

export const dynamic = 'force-dynamic'

export default async function InspectionContactsRoutePage() {
  const contacts = await fetchInspectionContactsServer()

  return <InspectionContactsPage contacts={contacts} />
}
