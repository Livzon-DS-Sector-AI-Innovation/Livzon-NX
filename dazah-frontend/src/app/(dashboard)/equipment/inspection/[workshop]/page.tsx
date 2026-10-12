import { notFound } from 'next/navigation'

import { FeishuInspectionPage } from '@/components/equipment/inspection/FeishuInspectionPage'
import { EQUIPMENT_WORKSHOPS } from '@/lib/menu-config'

export const dynamic = 'force-dynamic'

// 巡检数据按车间隔离：/equipment/inspection/<车间代码>
export default async function InspectionWorkshopPage({
  params,
}: {
  params: Promise<{ workshop: string }>
}) {
  const { workshop } = await params
  const meta = EQUIPMENT_WORKSHOPS.find((item) => item.code === workshop)
  if (!meta) notFound()
  return (
    <FeishuInspectionPage workshopCode={meta.code} workshopLabel={meta.label} />
  )
}
