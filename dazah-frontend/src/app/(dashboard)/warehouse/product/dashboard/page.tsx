import { WarehouseDashboard } from '@/components/warehouse'
import { fetchWarehouseDashboard } from '@/lib/api/server/warehouse'
import type { WarehouseDashboardData } from '@/types/warehouse'

export const dynamic = 'force-dynamic'

export default async function WarehouseProductDashboardPage() {
  let data: WarehouseDashboardData | null = null

  try {
    data = await fetchWarehouseDashboard('product', false, true)
  } catch (error) {
    console.warn('成品仪表盘初始数据加载失败，使用空数据降级:', error)
  }

  return <WarehouseDashboard group="product" title="成品库存仪表盘" baseName="成品" initialData={data} />
}
