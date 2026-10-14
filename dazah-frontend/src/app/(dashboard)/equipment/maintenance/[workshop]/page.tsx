import { notFound } from 'next/navigation'

import { MaintenancePage } from '@/components/equipment'
import {
  fetchEquipments, fetchWorkOrders, fetchWorkOrderStatistics, fetchFailureCodes,
  fetchCalibrationPlans, fetchCalibrationRecords,
  fetchMaintenancePlans,
} from '@/actions/equipment'
import { EQUIPMENT_WORKSHOPS } from '@/lib/menu-config'
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

// 维护保养按车间隔离：/equipment/maintenance/<车间代码>
export default async function MaintenancePageWrapper({
  params,
}: {
  params: Promise<{ workshop: string }>
}) {
  const { workshop } = await params
  const meta = EQUIPMENT_WORKSHOPS.find((item) => item.code === workshop)
  if (!meta) notFound()

  let equipments: Equipment[] = []
  let workOrders: WorkOrder[] = []
  let workOrderTotal = 0
  let workOrderStatistics = defaultStatistics
  let failureCodes: Record<'symptoms' | 'causes' | 'actions', FailureCode[]> = {
    symptoms: [],
    causes: [],
    actions: [],
  }
  let calibrationPlans: CalibrationPlan[] = []
  let calibrationPlanTotal = 0
  let calibrationRecords: CalibrationRecord[] = []
  let calibrationRecordTotal = 0
  let maintenancePlans: MaintenancePlan[] = []
  let maintenancePlanTotal = 0

  try {
    const result = await Promise.all([
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

    equipments = result[0].items
    workOrders = result[1].items
    workOrderTotal = result[1].total
    workOrderStatistics = result[2]
    failureCodes = {
      symptoms: result[3],
      causes: result[4],
      actions: result[5],
    }
    calibrationPlans = result[6].items
    calibrationPlanTotal = result[6].total
    calibrationRecords = result[7].items
    calibrationRecordTotal = result[7].total
    maintenancePlans = result[8].items
    maintenancePlanTotal = result[8].total
  } catch (error) {
    console.warn('维护模块数据加载失败，使用空数据:', error)
  }

  return (
    <MaintenancePage
      workshopCode={meta.code}
      workshopLabel={meta.label}
      initialEquipments={equipments}
      initialWorkOrders={workOrders}
      initialWorkOrderTotal={workOrderTotal}
      initialWorkOrderStatistics={workOrderStatistics}
      initialFailureCodes={failureCodes}
      initialCalibrationPlans={calibrationPlans}
      initialCalibrationPlanTotal={calibrationPlanTotal}
      initialCalibrationRecords={calibrationRecords}
      initialCalibrationRecordTotal={calibrationRecordTotal}
      initialMaintenancePlans={maintenancePlans}
      initialMaintenancePlanTotal={maintenancePlanTotal}
    />
  )
}
