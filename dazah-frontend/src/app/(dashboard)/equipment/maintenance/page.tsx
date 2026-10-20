import { MaintenancePage, WorkshopNavBlocks } from '@/components/equipment'
import {
  fetchEquipments, fetchWorkOrders, fetchWorkOrderStatistics, fetchFailureCodes,
  fetchCalibrationPlans, fetchCalibrationRecords,
  fetchMaintenancePlans,
} from '@/actions/equipment'
import { EQUIPMENT_WORKSHOPS } from '@/lib/menu-config'
import { EQUIPMENT_PAGE_KEYS } from '@/lib/equipment-page-permissions'
import {
  Equipment, FailureCode, WorkOrder, WorkOrderStatistics, CalibrationPlan, CalibrationRecord,
  MaintenancePlan,
} from '@/types/equipment'

export const dynamic = 'force-dynamic'

const defaultStatistics: WorkOrderStatistics = {
  total: 0,
  by_status: {} as any,
  by_type: {} as any,
  by_priority: {} as any,
}

// 维保单页 + 页内车间切换（?workshop=，缺省回落 201一车间）
export default async function MaintenancePageWrapper({
  searchParams,
}: {
  searchParams: Promise<{ workshop?: string }>
}) {
  const { workshop } = await searchParams
  const meta = EQUIPMENT_WORKSHOPS.find((item) => item.code === workshop)
    ?? EQUIPMENT_WORKSHOPS.find((item) => item.code === '201-1')!

  // 各域独立容错：任一接口失败只影响对应 Tab 的初始数据
  const [
    equipmentsRes, workOrdersRes, statsRes, symptomsRes, causesRes, actionsRes,
    calibrationPlansRes, calibrationRecordsRes, maintenancePlansRes,
  ] = await Promise.allSettled([
    fetchEquipments({ workshop: meta.code, page: 1, page_size: 200 }),
    fetchWorkOrders({ workshop: meta.code, page: 1, page_size: 20 }),
    fetchWorkOrderStatistics(meta.code),
    fetchFailureCodes('symptoms'),
    fetchFailureCodes('causes'),
    fetchFailureCodes('actions'),
    fetchCalibrationPlans({ workshop: meta.code, page: 1, page_size: 20 }),
    fetchCalibrationRecords({ workshop: meta.code, page: 1, page_size: 20 }),
    fetchMaintenancePlans({ workshop: meta.code, page: 1, page_size: 20 }),
  ])

  const equipments = equipmentsRes.status === 'fulfilled' ? equipmentsRes.value.items : []
  const workOrders = workOrdersRes.status === 'fulfilled' ? workOrdersRes.value.items : []
  const workOrderTotal = workOrdersRes.status === 'fulfilled' ? workOrdersRes.value.total : 0
  const workOrderStatistics = statsRes.status === 'fulfilled' ? statsRes.value : defaultStatistics
  const failureCodes: Record<'symptoms' | 'causes' | 'actions', FailureCode[]> = {
    symptoms: symptomsRes.status === 'fulfilled' ? symptomsRes.value : [],
    causes: causesRes.status === 'fulfilled' ? causesRes.value : [],
    actions: actionsRes.status === 'fulfilled' ? actionsRes.value : [],
  }
  const calibrationPlans = calibrationPlansRes.status === 'fulfilled' ? calibrationPlansRes.value.items : []
  const calibrationPlanTotal = calibrationPlansRes.status === 'fulfilled' ? calibrationPlansRes.value.total : 0
  const calibrationRecords = calibrationRecordsRes.status === 'fulfilled' ? calibrationRecordsRes.value.items : []
  const calibrationRecordTotal = calibrationRecordsRes.status === 'fulfilled' ? calibrationRecordsRes.value.total : 0
  const maintenancePlans = maintenancePlansRes.status === 'fulfilled' ? maintenancePlansRes.value.items : []
  const maintenancePlanTotal = maintenancePlansRes.status === 'fulfilled' ? maintenancePlansRes.value.total : 0

  return (
    <>
      <WorkshopNavBlocks pageKey={EQUIPMENT_PAGE_KEYS.maintenance} />
      <MaintenancePage
        workshopCode={meta.code}
        workshopLabel={meta.label}
        initialEquipments={equipments as Equipment[]}
        initialWorkOrders={workOrders as WorkOrder[]}
        initialWorkOrderTotal={workOrderTotal}
        initialWorkOrderStatistics={workOrderStatistics}
        initialFailureCodes={failureCodes}
        initialCalibrationPlans={calibrationPlans as CalibrationPlan[]}
        initialCalibrationPlanTotal={calibrationPlanTotal}
        initialCalibrationRecords={calibrationRecords as CalibrationRecord[]}
        initialCalibrationRecordTotal={calibrationRecordTotal}
        initialMaintenancePlans={maintenancePlans as MaintenancePlan[]}
        initialMaintenancePlanTotal={maintenancePlanTotal}
      />
    </>
  )
}
