import { fetchEmployeeStatsServer } from '@/lib/api/server/hr'
import { EmployeeDashboardClient } from '@/components/hr'
import type { EmployeeStats } from '@/types/hr'

export const dynamic = 'force-dynamic'

export default async function EmployeeManagementPage() {
  let stats: EmployeeStats = {}

  try {
    const res = await fetchEmployeeStatsServer()
    stats = res.data || {}
  } catch (error) {
    console.warn('员工统计数据加载失败:', error)
  }

  return <EmployeeDashboardClient stats={stats} />
}
