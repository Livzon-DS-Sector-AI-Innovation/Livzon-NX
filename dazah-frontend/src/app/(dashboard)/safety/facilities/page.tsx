import {
  getSafetyFacilities,
  getSafetyFacilityInspections,
  getSafetyFacilityStats,
} from '@/actions/safety'
import { SafetyFacilityPanel } from '@/components/safety'

export const dynamic = 'force-dynamic'

const PAGE_KEY = 'safety:site-mgmt:safety-facilities'

export default async function SafetyFacilitiesPage() {
  const [facilitiesRes, statsRes, recordsRes] = await Promise.all([
    getSafetyFacilities({ page_size: 200 }).catch(() => null),
    getSafetyFacilityStats().catch(() => null),
    getSafetyFacilityInspections({ page_size: 50 }).catch(() => null),
  ])

  const initialFacilities =
    facilitiesRes && facilitiesRes.code === 200 && facilitiesRes.data
      ? facilitiesRes.data.items
      : []
  const initialStats = statsRes && statsRes.code === 200 ? statsRes.data : null
  const initialRecords =
    recordsRes && recordsRes.code === 200 && recordsRes.data
      ? recordsRes.data.items
      : []
  const initialError =
    facilitiesRes && facilitiesRes.code !== 200
      ? facilitiesRes.message || '加载安全设施失败'
      : null

  return (
    <SafetyFacilityPanel
      pageKey={PAGE_KEY}
      initialFacilities={initialFacilities}
      initialStats={initialStats}
      initialRecords={initialRecords}
      initialError={initialError}
    />
  )
}
