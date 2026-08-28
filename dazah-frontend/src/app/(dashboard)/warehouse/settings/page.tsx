import { WarehouseFeishuConfigPage } from '@/components/warehouse'
import { fetchWarehousePageFeishuConfigs } from '@/lib/api/server/warehouse'
import type { WarehousePageFeishuConfig } from '@/types/warehouse'

export const dynamic = 'force-dynamic'

export default async function WarehouseSettingsPage() {
  let configs: WarehousePageFeishuConfig[] = []
  try {
    configs = await fetchWarehousePageFeishuConfigs()
  } catch (error) {
    console.warn('获取页面飞书配置失败:', error)
  }

  return <WarehouseFeishuConfigPage initialConfigs={configs} />
}
