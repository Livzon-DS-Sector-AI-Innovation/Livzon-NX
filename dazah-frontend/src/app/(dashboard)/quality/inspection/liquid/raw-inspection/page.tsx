import { redirect } from 'next/navigation'

import { liquidInspectionGroups } from '@/lib/quality-inspection-material-groups'

export const dynamic = 'force-dynamic'

export default function LiquidRawInspectionPage() {
  redirect(`/quality/inspection/liquid/${liquidInspectionGroups[0].key}`)
}
