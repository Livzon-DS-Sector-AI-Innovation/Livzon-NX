import SpecialOpsManagement from '@/components/safety/SpecialOpsManagement'
import {
  getSpecialOperationLedgerStats,
  getSpecialOperationReports,
} from '@/actions/safety'
import type {
  SpecialOperationLedgerStats,
  SpecialOperationReport,
} from '@/types/safety'

export const dynamic = 'force-dynamic'

/** 工厂所在地当天（避免服务器 UTC 时区跨日偏差）。 */
function todayInFactoryZone(): string {
  return new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
}

export default async function SpecialOpsPage() {
  // 首屏在服务端直出「当天」数据与统计：台账默认当天，避免首屏空表
  const today = todayInFactoryZone()
  let initialStats: SpecialOperationLedgerStats[] = []
  let initialData: SpecialOperationReport[] = []
  let initialTotal = 0
  try {
    const [statsRes, listRes] = await Promise.all([
      getSpecialOperationLedgerStats({ date_from: today, date_to: today }),
      getSpecialOperationReports({
        page: 1,
        page_size: 20,
        date_from: today,
        date_to: today,
      }),
    ])
    if (statsRes.code === 200) initialStats = statsRes.data || []
    if (listRes.code === 200) {
      initialData = listRes.data || []
      initialTotal = listRes.meta?.total || 0
    }
  } catch {
    // 服务端取数失败时交给客户端兜底重试
  }

  return (
    <SpecialOpsManagement
      initialStats={initialStats}
      initialData={initialData}
      initialTotal={initialTotal}
      initialDateFilter={today}
    />
  )
}
