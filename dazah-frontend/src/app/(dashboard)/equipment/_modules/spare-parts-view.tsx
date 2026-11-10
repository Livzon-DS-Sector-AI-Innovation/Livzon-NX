import { SparePartsPage } from '@/components/equipment'
import { EquipmentQueryFailure, isEquipmentQueryAccessError } from '@/components/equipment/EquipmentQueryFailure'
import { fetchSpareParts, fetchStockWarnings } from '@/actions/equipment'
import { SparePart, StockWarning } from '@/types/equipment'

// 备件模块：鉴权失败显示访问状态，其他失败保留原有容错。
export default async function SparePartsView({
  workshopCode,
}: {
  workshopCode: string
}) {
  let spareParts: SparePart[] = []
  let sparePartTotal = 0
  let stockWarnings: StockWarning[] = []

  try {
    const result = await Promise.all([
      fetchSpareParts({ workshop: workshopCode, page: 1, page_size: 20 }),
      fetchStockWarnings(workshopCode),
    ])
    spareParts = result[0].items
    sparePartTotal = result[0].total
    stockWarnings = result[1]
  } catch (error) {
    if (isEquipmentQueryAccessError(error)) return <EquipmentQueryFailure status={error.status} />
    console.warn('备件管理数据加载失败，使用空数据:', error)
  }

  return (
    <SparePartsPage
      workshopCode={workshopCode}
      initialSpareParts={spareParts}
      initialSparePartTotal={sparePartTotal}
      initialStockWarnings={stockWarnings}
    />
  )
}
