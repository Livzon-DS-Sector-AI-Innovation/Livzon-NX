import { WarehouseSettingsTabs } from '@/components/warehouse/WarehouseSettingsTabs'
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

  return (
    <main className="mx-auto max-w-[1440px] px-6 py-7">
      <h1 className="mb-5 text-[22px] font-semibold text-[var(--color-charcoal)]">仓储设置</h1>
      <WarehouseSettingsTabs initialConfigs={configs} />
    </main>
  )
}
