import { WarehouseDashboard } from '@/components/warehouse'
import { fetchWarehouseDashboard } from '@/lib/api/server/warehouse'
import type { WarehouseDashboardData } from '@/types/warehouse'

export const dynamic = 'force-dynamic'

export default async function WarehouseHardwareDashboardPage() {
  let data: WarehouseDashboardData | null = null

  try {
    data = await fetchWarehouseDashboard('hardware', false, true)
  } catch (error) {
    console.warn('五金仪表盘初始数据加载失败，使用空数据降级:', error)
  }

  return <WarehouseDashboard group="hardware" title="五金仪表盘" baseName="五金" initialData={data} />
}
