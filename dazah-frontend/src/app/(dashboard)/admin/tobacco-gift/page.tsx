import { TobaccoGiftDashboard } from '@/components/administration'
import { TOBACCO_GIFT_DASHBOARD_PAGE_KEY } from '@/lib/administration-pages'
import { fetchTobaccoGiftDashboardStats } from '@/lib/api/server/administration'
import type { TobaccoGiftDashboardStats } from '@/types/administration'

export const dynamic = 'force-dynamic'

export default async function TobaccoGiftDashboardPage() {
  let stats: TobaccoGiftDashboardStats | null = null
  let error: string | null = null
  try {
    stats = await fetchTobaccoGiftDashboardStats(TOBACCO_GIFT_DASHBOARD_PAGE_KEY)
  } catch (cause) {
    error = cause instanceof Error ? cause.message : '读取烟酒礼品统计失败'
  }
  return <TobaccoGiftDashboard stats={stats} error={error} />
}
