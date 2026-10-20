import { WorkshopNavBlocks } from '@/components/equipment'
import { FeishuInspectionPage } from '@/components/equipment/inspection/FeishuInspectionPage'
import { EQUIPMENT_WORKSHOPS } from '@/lib/menu-config'
import { EQUIPMENT_PAGE_KEYS } from '@/lib/equipment-page-permissions'

export const dynamic = 'force-dynamic'

// 巡检单页 + 页内车间切换（?workshop=，缺省回落 201一车间）；数据在客户端自取
export default async function InspectionPage({
  searchParams,
}: {
  searchParams: Promise<{ workshop?: string }>
}) {
  const { workshop } = await searchParams
  const meta = EQUIPMENT_WORKSHOPS.find((item) => item.code === workshop)
    ?? EQUIPMENT_WORKSHOPS.find((item) => item.code === '201-1')!

  return (
    <>
      <WorkshopNavBlocks pageKey={EQUIPMENT_PAGE_KEYS.inspection} />
      <FeishuInspectionPage workshopCode={meta.code} workshopLabel={meta.label} />
    </>
  )
}
