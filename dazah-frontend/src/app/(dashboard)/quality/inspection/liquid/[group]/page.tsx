import { notFound } from 'next/navigation'

import { QualityQueryProvider } from '@/components/quality'
import { InspectionGroupSubtablePage } from '@/components/quality/inspection'
import { getLiquidInspectionGroupLabel } from '@/lib/quality-inspection-material-groups'

export const dynamic = 'force-dynamic'

export default async function LiquidInspectionGroupPage({
  params,
}: {
  params: Promise<{ group: string }>
}) {
  const { group } = await params
  const title = getLiquidInspectionGroupLabel(group)

  if (!title) {
    notFound()
  }

  return (
    <QualityQueryProvider>
      <InspectionGroupSubtablePage title={title} module="liquid" group={group} />
    </QualityQueryProvider>
  )
}
