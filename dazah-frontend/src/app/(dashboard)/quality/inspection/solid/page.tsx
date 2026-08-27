import { redirect } from 'next/navigation'

import { solidInspectionGroups } from '@/lib/quality-inspection-material-groups'

export const dynamic = 'force-dynamic'

export default function InspectionSolidPage() {
  redirect(`/quality/inspection/solid/${solidInspectionGroups[0].key}`)
}
