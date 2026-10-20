import { MaintenancePage } from '@/components/equipment'
import {
  fetchEquipments, fetchWorkOrders, fetchWorkOrderStatistics, fetchFailureCodes,
  fetchCalibrationPlans, fetchCalibrationRecords,
  fetchMaintenancePlans,
} from '@/actions/equipment'
import {
  Equipment, FailureCode, WorkOrder, WorkOrderStatistics, CalibrationPlan, CalibrationRecord,
  MaintenancePlan,
} from '@/types/equipment'

const defaultStatistics: WorkOrderStatistics = {
  total: 0,
  by_status: {} as any,
  by_type: {} as any,
  by_priority: {} as any,
}

// 维保模块：各域独立容错，任一接口失败只影响对应 Tab 的初始数据
export default async function MaintenanceView({
  workshopCode,
}: {
  workshopCode: string
}) {
  const [
    equipmentsRes, workOrdersRes, statsRes, symptomsRes, causesRes, actionsRes,
    calibrationPlansRes, calibrationRecordsRes, maintenancePlansRes,
  ] = await Promise.allSettled([
    fetchEquipments({ workshop: workshopCode, page: 1, page_size: 200 }),
    fetchWorkOrders({ workshop: workshopCode, page: 1, page_size: 20 }),
    fetchWorkOrderStatistics(workshopCode),
    fetchFailureCodes('symptoms'),
    fetchFailureCodes('causes'),
    fetchFailureCodes('actions'),
    fetchCalibrationPlans({ workshop: workshopCode, page: 1, page_size: 20 }),
    fetchCalibrationRecords({ workshop: workshopCode, page: 1, page_size: 20 }),
    fetchMaintenancePlans({ workshop: workshopCode, page: 1, page_size: 20 }),
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
    <MaintenancePage
      workshopCode={workshopCode}
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
  )
}
