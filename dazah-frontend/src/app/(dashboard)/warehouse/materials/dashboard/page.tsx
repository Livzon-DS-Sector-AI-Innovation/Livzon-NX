import { WarehouseDashboard } from '@/components/warehouse'
import { fetchWarehouseDashboard } from '@/lib/api/server/warehouse'
import type { WarehouseDashboardData } from '@/types/warehouse'

export const dynamic = 'force-dynamic'

export default async function WarehouseMaterialsDashboardPage() {
  let data: WarehouseDashboardData | null = null

  try {
    data = await fetchWarehouseDashboard('raw', false, true)
  } catch (error) {
    console.warn('原辅料仪表盘初始数据加载失败，使用空数据降级:', error)
  }

  return <WarehouseDashboard group="raw" title="原辅料及包材仪表盘" baseName="原辅料" initialData={data} />
}
