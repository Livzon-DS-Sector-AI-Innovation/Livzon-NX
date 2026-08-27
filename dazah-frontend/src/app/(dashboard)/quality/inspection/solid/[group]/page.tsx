import { notFound } from 'next/navigation'

import { QualityQueryProvider } from '@/components/quality'
import { InspectionGroupSubtablePage } from '@/components/quality/inspection'
import { getSolidInspectionGroupLabel } from '@/lib/quality-inspection-material-groups'

export const dynamic = 'force-dynamic'

export default async function SolidInspectionGroupPage({
  params,
}: {
  params: Promise<{ group: string }>
}) {
  const { group } = await params
  const title = getSolidInspectionGroupLabel(group)

  if (!title) {
    notFound()
  }

  return (
    <QualityQueryProvider>
      <InspectionGroupSubtablePage title={title} module="solid" group={group} />
    </QualityQueryProvider>
  )
}
