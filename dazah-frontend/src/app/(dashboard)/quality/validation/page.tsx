import { ValidationDashboardClient } from '@/components/quality'
import { fetchFeishuValidationDashboardStatsServer } from '@/lib/api/server/quality'


export const dynamic = 'force-dynamic'

export default async function QualityValidationDashboardPage() {
  let stats = null
  try {
    stats = await fetchFeishuValidationDashboardStatsServer()
  } catch {
    // 数据加载失败时显示空状态
  }

  return <ValidationDashboardClient initialStats={stats} />
}
