import { EquipmentPage } from '@/components/equipment'
import { EquipmentQueryFailure, isEquipmentQueryAccessError } from '@/components/equipment/EquipmentQueryFailure'
import {
  fetchEquipments,
  fetchEquipmentStatistics,
  fetchDepartments,
} from '@/actions/equipment'

// 台账模块：设备列表 SSR 预取；分类/位置由客户端自行加载
const defaultStatistics: Record<string, unknown> = {
  total: 0,
  by_status: { '在用': 0, '备用': 0, '维修中': 0, '停用': 0, '报废': 0 },
  by_category: {},
  by_location: {},
}

export default async function AssetsView({ workshopCode }: { workshopCode: string }) {
  const [equipmentsResult, statsResult, departmentsResult] = await Promise.allSettled([
    fetchEquipments({ workshop: workshopCode, page: 1, page_size: 20 }),
    fetchEquipmentStatistics(workshopCode),
    fetchDepartments(),
  ])

  const equipments = equipmentsResult.status === 'fulfilled' ? equipmentsResult.value : null
  const stats = statsResult.status === 'fulfilled' ? statsResult.value : null
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const initialEquipments: any[] = equipments?.code === 200 ? equipments.data?.items ?? [] : []
  const initialTotal: number = equipments?.code === 200 ? equipments.data?.total ?? 0 : 0
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const initialStatistics: any = stats?.code === 200 ? stats.data ?? defaultStatistics : defaultStatistics
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const initialDepartments: any[] = departmentsResult.status === 'fulfilled' ? departmentsResult.value : []

  const hasAccessError =
    (equipmentsResult.status === 'rejected' && isEquipmentQueryAccessError(equipmentsResult.reason)) ||
    (statsResult.status === 'rejected' && isEquipmentQueryAccessError(statsResult.reason))

  const rejectedReason =
    equipmentsResult.status === 'rejected' ? equipmentsResult.reason :
    statsResult.status === 'rejected' ? statsResult.reason :
    null
  const accessErrorStatus =
    rejectedReason && 'status' in rejectedReason && (rejectedReason as { status: number }).status === 401
      ? 401
      : 403

  if (hasAccessError) {
    return <EquipmentQueryFailure status={accessErrorStatus as 401 | 403} />
  }

  return (
    <EquipmentPage
      workshopCode={workshopCode}
      initialCategories={[]}
      initialLocations={[]}
      initialEquipments={initialEquipments}
      initialTotal={initialTotal}
      initialStatistics={initialStatistics}
      initialDepartments={initialDepartments}
    />
  )
}
