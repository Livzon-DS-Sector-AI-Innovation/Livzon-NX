import { notFound } from 'next/navigation'

import { SparePartsPage } from '@/components/equipment'
import { fetchSpareParts, fetchStockWarnings } from '@/actions/equipment'
import { EQUIPMENT_WORKSHOPS } from '@/lib/menu-config'
import { SparePart, StockWarning } from '@/types/equipment'

export const dynamic = 'force-dynamic'

// 备件按车间隔离：/equipment/spare-parts/<车间代码>
export default async function SparePartsPageWrapper({
  params,
}: {
  params: Promise<{ workshop: string }>
}) {
  const { workshop } = await params
  const meta = EQUIPMENT_WORKSHOPS.find((item) => item.code === workshop)
  if (!meta) notFound()

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
    <SparePartsPage
      workshopCode={meta.code}
      workshopLabel={meta.label}
      initialSpareParts={spareParts}
      initialSparePartTotal={sparePartTotal}
      initialStockWarnings={stockWarnings}
    />
  )
}
