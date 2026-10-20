import { SparePartsPage, WorkshopNavBlocks } from '@/components/equipment'
import { fetchSpareParts, fetchStockWarnings } from '@/actions/equipment'
import { EQUIPMENT_WORKSHOPS } from '@/lib/menu-config'
import { EQUIPMENT_PAGE_KEYS } from '@/lib/equipment-page-permissions'
import { SparePart, StockWarning } from '@/types/equipment'

export const dynamic = 'force-dynamic'

// 备件单页 + 页内车间切换（?workshop=，缺省回落 201一车间）
export default async function SparePartsPageWrapper({
  searchParams,
}: {
  searchParams: Promise<{ workshop?: string }>
}) {
  const { workshop } = await searchParams
  const meta = EQUIPMENT_WORKSHOPS.find((item) => item.code === workshop)
    ?? EQUIPMENT_WORKSHOPS.find((item) => item.code === '201-1')!

  let spareParts: SparePart[] = []
  let sparePartTotal = 0
  let stockWarnings: StockWarning[] = []

  try {
    const result = await Promise.all([
      fetchSpareParts({ workshop: meta.code, page: 1, page_size: 20 }),
      fetchStockWarnings(meta.code),
    ])
    spareParts = result[0].items
    sparePartTotal = result[0].total
    stockWarnings = result[1]
  } catch (error) {
    console.warn('备件管理数据加载失败，使用空数据:', error)
  }

  return (
    <>
      <WorkshopNavBlocks pageKey={EQUIPMENT_PAGE_KEYS.spareParts} />
      <SparePartsPage
        workshopCode={meta.code}
        workshopLabel={meta.label}
        initialSpareParts={spareParts}
        initialSparePartTotal={sparePartTotal}
        initialStockWarnings={stockWarnings}
      />
    </>
  )
}
