import {
  getEmergencyDrills,
  getEmergencyPlans,
  getEmergencySupplies,
} from '@/actions/safety'
import { EmergencyMgmtPanel } from '@/components/safety'

export const dynamic = 'force-dynamic'

const PAGE_KEY = 'safety:emergency-accident:emergency-mgmt'

export default async function EmergencyMgmtPage() {
  const [plansRes, drillsRes, suppliesRes] = await Promise.all([
    getEmergencyPlans({ page_size: 200 }).catch(() => null),
    getEmergencyDrills({ page_size: 200 }).catch(() => null),
    getEmergencySupplies({ page_size: 200 }).catch(() => null),
  ])

  const initialPlans =
    plansRes && plansRes.code === 200 && plansRes.data ? plansRes.data.items : []
  const initialDrills =
    drillsRes && drillsRes.code === 200 && drillsRes.data ? drillsRes.data.items : []
  const initialSupplies =
    suppliesRes && suppliesRes.code === 200 && suppliesRes.data
      ? suppliesRes.data.items
      : []
  const initialError =
    plansRes && plansRes.code !== 200
      ? plansRes.message || '加载应急管理数据失败'
      : null

  return (
    <EmergencyMgmtPanel
      pageKey={PAGE_KEY}
      initialPlans={initialPlans}
      initialDrills={initialDrills}
      initialSupplies={initialSupplies}
      initialError={initialError}
    />
  )
}
