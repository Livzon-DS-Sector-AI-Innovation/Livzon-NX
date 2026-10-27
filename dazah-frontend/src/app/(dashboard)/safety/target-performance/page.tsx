import {
  getSafetyTargets,
  getSafetyTargetStats,
} from '@/actions/safety'
import { TargetPerformancePanel } from '@/components/safety'

export const dynamic = 'force-dynamic'

const PAGE_KEY = 'safety:governance:target-performance'

export default async function TargetPerformancePage() {
  const [targetsRes, statsRes] = await Promise.all([
    getSafetyTargets({ page_size: 200 }).catch(() => null),
    getSafetyTargetStats().catch(() => null),
  ])

  const initialTargets =
    targetsRes && targetsRes.code === 200 && targetsRes.data
      ? targetsRes.data.items
      : []
  const initialStats =
    statsRes && statsRes.code === 200 ? statsRes.data : null
  const initialError =
    targetsRes && targetsRes.code !== 200
      ? targetsRes.message || '加载安全目标失败'
      : null

  return (
    <TargetPerformancePanel
      pageKey={PAGE_KEY}
      initialTargets={initialTargets}
      initialStats={initialStats}
      initialError={initialError}
    />
  )
}
