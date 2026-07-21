import { create } from 'zustand'
import { devtools } from 'zustand/middleware'
import {
  EquipmentCategory,
  Location,
  Equipment,
  EquipmentStatus,
  EquipmentStatistics,
  FailureCode,
  WorkOrder,
  WorkOrderStatus,
  WorkOrderPriority,
  WorkOrderType,
  WorkOrderStatistics,
  CalibrationPlan,
  CalibrationPlanStatus,
  CalibrationRecord,
  SparePart,
  StockWarning,
  MaintenancePlan,
  MaintenancePlanStatus,
  InspectionTemplate,
  InspectionTemplateItem,
  Maintainer,
  DepartmentOption,
} from '@/types/equipment'

interface EquipmentStore {
  // 数据
  categories: EquipmentCategory[]
  locations: Location[]
  equipments: Equipment[]
  statistics: EquipmentStatistics | null

  // 筛选状态
  selectedCategory: string | null
  selectedLocation: string | null
  statusFilter: EquipmentStatus | ''
  departmentFilter: string | null
  departments: DepartmentOption[]
  setDepartmentFilter: (id: string | null) => void
  setDepartments: (departments: DepartmentOption[]) => void
  keyword: string
  page: number
  pageSize: number
  total: number
  loading: boolean

  // 抽屉状态
  equipmentDrawerOpen: boolean
  categoryDrawerOpen: boolean
  locationDrawerOpen: boolean
  editingEquipment: Equipment | null
  editingCategory: EquipmentCategory | null
  editingLocation: Location | null

  // 操作
  setCategories: (categories: EquipmentCategory[]) => void
  setLocations: (locations: Location[]) => void
  setEquipments: (equipments: Equipment[]) => void
  setStatistics: (statistics: EquipmentStatistics | null) => void
  setSelectedCategory: (id: string | null) => void
  setSelectedLocation: (id: string | null) => void
  setStatusFilter: (status: EquipmentStatus | '') => void
  setKeyword: (keyword: string) => void
  setPage: (page: number) => void
  setPageSize: (pageSize: number) => void
  setTotal: (total: number) => void
  setLoading: (loading: boolean) => void
  resetFilters: () => void
  openEquipmentDrawer: (equipment?: Equipment) => void
  closeEquipmentDrawer: () => void
  openCategoryDrawer: (category?: EquipmentCategory) => void
  closeCategoryDrawer: () => void
  openLocationDrawer: (location?: Location) => void
  closeLocationDrawer: () => void

  // ========== 维护模块 ==========
  maintenanceTab: string
  setMaintenanceTab: (tab: string) => void

  // 工单
  workOrders: WorkOrder[]
  workOrderTotal: number
  workOrderPage: number
  workOrderPageSize: number
  workOrderStatistics: WorkOrderStatistics | null
  workOrderLoading: boolean
  workOrderStatusFilter: WorkOrderStatus | ''
  workOrderPriorityFilter: WorkOrderPriority | ''
  workOrderTypeFilter: WorkOrderType | ''
  setWorkOrders: (orders: WorkOrder[]) => void
  setWorkOrderTotal: (total: number) => void
  setWorkOrderPage: (page: number) => void
  setWorkOrderPageSize: (size: number) => void
  setWorkOrderStatistics: (stats: WorkOrderStatistics | null) => void
  setWorkOrderLoading: (loading: boolean) => void
  setWorkOrderStatusFilter: (status: WorkOrderStatus | '') => void
  setWorkOrderPriorityFilter: (priority: WorkOrderPriority | '') => void
  setWorkOrderTypeFilter: (type: WorkOrderType | '') => void
  workOrderDrawerOpen: boolean
  workOrderDetailOpen: boolean
  editingWorkOrder: WorkOrder | null
  viewingWorkOrder: WorkOrder | null
  setViewingWorkOrder: (order: WorkOrder | null) => void
  openWorkOrderDrawer: (order?: WorkOrder) => void
  closeWorkOrderDrawer: () => void
  openWorkOrderDetail: (order: WorkOrder) => void
  closeWorkOrderDetail: () => void

  // 故障代码
  failureCodes: Record<'symptoms' | 'causes' | 'actions', FailureCode[]>
  failureCodeLoading: boolean
  setFailureCodes: (type: 'symptoms' | 'causes' | 'actions', codes: FailureCode[]) => void
  setFailureCodeLoading: (loading: boolean) => void
  failureCodeDrawerOpen: boolean
  failureCodeDrawerType: 'symptoms' | 'causes' | 'actions'
  editingFailureCode: FailureCode | null
  openFailureCodeDrawer: (type: 'symptoms' | 'causes' | 'actions', code?: FailureCode) => void
  closeFailureCodeDrawer: () => void

  // 校准计划
  calibrationPlans: CalibrationPlan[]
  calibrationPlanTotal: number
  calibrationPlanPage: number
  calibrationPlanPageSize: number
  calibrationPlanLoading: boolean
  calibrationPlanStatusFilter: CalibrationPlanStatus | ''
  setCalibrationPlans: (plans: CalibrationPlan[]) => void
  setCalibrationPlanTotal: (total: number) => void
  setCalibrationPlanPage: (page: number) => void
  setCalibrationPlanPageSize: (size: number) => void
  setCalibrationPlanLoading: (loading: boolean) => void
  setCalibrationPlanStatusFilter: (status: CalibrationPlanStatus | '') => void
  calibrationPlanDrawerOpen: boolean
  editingCalibrationPlan: CalibrationPlan | null
  openCalibrationPlanDrawer: (plan?: CalibrationPlan) => void
  closeCalibrationPlanDrawer: () => void

  // 校准记录
  calibrationRecords: CalibrationRecord[]
  calibrationRecordTotal: number
  calibrationRecordPage: number
  calibrationRecordPageSize: number
  calibrationRecordLoading: boolean
  setCalibrationRecords: (records: CalibrationRecord[]) => void
  setCalibrationRecordTotal: (total: number) => void
  setCalibrationRecordPage: (page: number) => void
  setCalibrationRecordPageSize: (size: number) => void
  setCalibrationRecordLoading: (loading: boolean) => void
  calibrationRecordDrawerOpen: boolean
  editingCalibrationRecord: CalibrationRecord | null
  openCalibrationRecordDrawer: (record?: CalibrationRecord) => void
  closeCalibrationRecordDrawer: () => void

  // ========== 备件管理 ==========
  spareParts: SparePart[]
  sparePartTotal: number
  sparePartPage: number
  sparePartPageSize: number
  sparePartLoading: boolean
  sparePartKeyword: string
  stockWarnings: StockWarning[]
  stockWarningsLoading: boolean
  setSpareParts: (parts: SparePart[]) => void
  setSparePartTotal: (total: number) => void
  setSparePartPage: (page: number) => void
  setSparePartPageSize: (size: number) => void
  setSparePartLoading: (loading: boolean) => void
  setSparePartKeyword: (keyword: string) => void
  setStockWarnings: (warnings: StockWarning[]) => void
  setStockWarningsLoading: (loading: boolean) => void
  sparePartDrawerOpen: boolean
  editingSparePart: SparePart | null
  openSparePartDrawer: (part?: SparePart) => void
  closeSparePartDrawer: () => void
  stockInboundDrawerOpen: boolean
  stockInboundSparePartId: string | null
  openStockInboundDrawer: (sparePartId: string) => void
  closeStockInboundDrawer: () => void

  // ========== 维护计划 ==========
  maintenancePlans: MaintenancePlan[]
  maintenancePlanTotal: number
  maintenancePlanPage: number
  maintenancePlanPageSize: number
  maintenancePlanLoading: boolean
  maintenancePlanStatusFilter: MaintenancePlanStatus | ''
  maintenancePlanKeyword: string
  setMaintenancePlans: (plans: MaintenancePlan[]) => void
  setMaintenancePlanTotal: (total: number) => void
  setMaintenancePlanPage: (page: number) => void
  setMaintenancePlanPageSize: (size: number) => void
  setMaintenancePlanLoading: (loading: boolean) => void
  setMaintenancePlanStatusFilter: (status: MaintenancePlanStatus | '') => void
  setMaintenancePlanKeyword: (keyword: string) => void
  maintenancePlanDrawerOpen: boolean
  editingMaintenancePlan: MaintenancePlan | null
  openMaintenancePlanDrawer: (plan?: MaintenancePlan) => void
  closeMaintenancePlanDrawer: () => void

  // ========== 巡检模板 ==========
  inspectionTemplates: InspectionTemplate[]
  inspectionTemplateTotal: number
  inspectionTemplatePage: number
  inspectionTemplatePageSize: number
  inspectionTemplateLoading: boolean
  inspectionTemplateKeyword: string
  setInspectionTemplates: (templates: InspectionTemplate[]) => void
  setInspectionTemplateTotal: (total: number) => void
  setInspectionTemplatePage: (page: number) => void
  setInspectionTemplatePageSize: (size: number) => void
  setInspectionTemplateLoading: (loading: boolean) => void
  setInspectionTemplateKeyword: (keyword: string) => void
  inspectionTemplateDrawerOpen: boolean
  editingInspectionTemplate: InspectionTemplate | null
  openInspectionTemplateDrawer: (template?: InspectionTemplate) => void
  closeInspectionTemplateDrawer: () => void
  inspectionItemDrawerOpen: boolean
  inspectionItemTemplateId: string | null
  editingInspectionItem: InspectionTemplateItem | null
  openInspectionItemDrawer: (templateId: string, item?: InspectionTemplateItem) => void
  closeInspectionItemDrawer: () => void

  // ========== 巡检完成 ==========
  inspectionCompleteDrawerOpen: boolean
  completingWorkOrderId: string | null
  completingTemplateName: string | null
  completingTemplateItems: InspectionTemplateItem[]
  openInspectionCompleteDrawer: (workOrderId: string, templateName: string, items: InspectionTemplateItem[]) => void
  closeInspectionCompleteDrawer: () => void

  // ========== 报修抽屉 ==========
  repairDrawerOpen: boolean
  repairEquipmentId: string | null
  openRepairDrawer: (equipmentId: string) => void
  closeRepairDrawer: () => void

  // ========== 超时配置 ==========
  claimTimeoutConfig: { emergency: number; high: number; medium: number; low: number }
  setClaimTimeoutConfig: (config: { emergency: number; high: number; medium: number; low: number }) => void

  // ========== 维修人员 ==========
  maintainers: Maintainer[]
  setMaintainers: (maintainers: Maintainer[]) => void
}

export const useEquipmentStore = create<EquipmentStore>()(
  devtools(
    (set) => ({
      // 初始状态
      categories: [],
      locations: [],
      equipments: [],
      statistics: null,
      selectedCategory: null,
      selectedLocation: null,
      statusFilter: '',
      departmentFilter: null,
      departments: [],
      keyword: '',
      page: 1,
      pageSize: 20,
      total: 0,
      loading: false,
      equipmentDrawerOpen: false,
      categoryDrawerOpen: false,
      locationDrawerOpen: false,
      editingEquipment: null,
      editingCategory: null,
      editingLocation: null,

      // 操作
      setCategories: (categories) => set({ categories }, false, 'equipment/setCategories'),
      setLocations: (locations) => set({ locations }, false, 'equipment/setLocations'),
      setEquipments: (equipments) => set({ equipments }, false, 'equipment/setEquipments'),
      setStatistics: (statistics) => set({ statistics }, false, 'equipment/setStatistics'),
      setSelectedCategory: (id) => set({ selectedCategory: id, page: 1 }, false, 'equipment/setSelectedCategory'),
      setSelectedLocation: (id) => set({ selectedLocation: id, page: 1 }, false, 'equipment/setSelectedLocation'),
      setStatusFilter: (status) => set({ statusFilter: status, page: 1 }, false, 'equipment/setStatusFilter'),
      setDepartmentFilter: (id) => set({ departmentFilter: id, page: 1 }, false, 'equipment/setDepartmentFilter'),
      setDepartments: (departments) => set({ departments }, false, 'equipment/setDepartments'),
      setKeyword: (keyword) => set({ keyword, page: 1 }, false, 'equipment/setKeyword'),
      setPage: (page) => set({ page }, false, 'equipment/setPage'),
      setPageSize: (pageSize) => set({ pageSize, page: 1 }, false, 'equipment/setPageSize'),
      setTotal: (total) => set({ total }, false, 'equipment/setTotal'),
      setLoading: (loading) => set({ loading }, false, 'equipment/setLoading'),
      resetFilters: () => set({
        selectedCategory: null,
        selectedLocation: null,
        departmentFilter: null,
        statusFilter: '',
        keyword: '',
        page: 1,
        pageSize: 20,
      }, false, 'equipment/resetFilters'),
      openEquipmentDrawer: (equipment) =>
        set({
          equipmentDrawerOpen: true,
          editingEquipment: equipment || null,
        }, false, 'equipment/openEquipmentDrawer'),
      closeEquipmentDrawer: () =>
        set({
          equipmentDrawerOpen: false,
          editingEquipment: null,
        }, false, 'equipment/closeEquipmentDrawer'),
      openCategoryDrawer: (category) =>
        set({
          categoryDrawerOpen: true,
          editingCategory: category || null,
        }, false, 'equipment/openCategoryDrawer'),
      closeCategoryDrawer: () =>
        set({
          categoryDrawerOpen: false,
          editingCategory: null,
        }, false, 'equipment/closeCategoryDrawer'),
      openLocationDrawer: (location) =>
        set({
          locationDrawerOpen: true,
          editingLocation: location || null,
        }, false, 'equipment/openLocationDrawer'),
      closeLocationDrawer: () =>
        set({
          locationDrawerOpen: false,
          editingLocation: null,
        }, false, 'equipment/closeLocationDrawer'),

      // ========== 维护模块 ==========
      maintenanceTab: 'work-orders',
      setMaintenanceTab: (tab) => set({ maintenanceTab: tab }, false, 'equipment/setMaintenanceTab'),

      // 工单
      workOrders: [],
      workOrderTotal: 0,
      workOrderPage: 1,
      workOrderPageSize: 20,
      workOrderStatistics: null,
      workOrderLoading: false,
      workOrderStatusFilter: '',
      workOrderPriorityFilter: '',
      workOrderTypeFilter: '',
      setWorkOrders: (orders) => set({ workOrders: orders }, false, 'equipment/setWorkOrders'),
      setWorkOrderTotal: (total) => set({ workOrderTotal: total }, false, 'equipment/setWorkOrderTotal'),
      setWorkOrderPage: (page) => set({ workOrderPage: page }, false, 'equipment/setWorkOrderPage'),
      setWorkOrderPageSize: (size) => set({ workOrderPageSize: size, workOrderPage: 1 }, false, 'equipment/setWorkOrderPageSize'),
      setWorkOrderStatistics: (stats) => set({ workOrderStatistics: stats }, false, 'equipment/setWorkOrderStatistics'),
      setWorkOrderLoading: (loading) => set({ workOrderLoading: loading }, false, 'equipment/setWorkOrderLoading'),
      setWorkOrderStatusFilter: (status) => set({ workOrderStatusFilter: status, workOrderPage: 1 }, false, 'equipment/setWorkOrderStatusFilter'),
      setWorkOrderPriorityFilter: (priority) => set({ workOrderPriorityFilter: priority, workOrderPage: 1 }, false, 'equipment/setWorkOrderPriorityFilter'),
      setWorkOrderTypeFilter: (type) => set({ workOrderTypeFilter: type, workOrderPage: 1 }, false, 'equipment/setWorkOrderTypeFilter'),
      workOrderDrawerOpen: false,
      workOrderDetailOpen: false,
      editingWorkOrder: null,
      viewingWorkOrder: null,
      setViewingWorkOrder: (order) => set({ viewingWorkOrder: order }, false, 'equipment/setViewingWorkOrder'),
      openWorkOrderDrawer: (order) => set({ workOrderDrawerOpen: true, editingWorkOrder: order || null }, false, 'equipment/openWorkOrderDrawer'),
      closeWorkOrderDrawer: () => set({ workOrderDrawerOpen: false, editingWorkOrder: null }, false, 'equipment/closeWorkOrderDrawer'),
      openWorkOrderDetail: (order) => set({ workOrderDetailOpen: true, viewingWorkOrder: order }, false, 'equipment/openWorkOrderDetail'),
      closeWorkOrderDetail: () => set({ workOrderDetailOpen: false, viewingWorkOrder: null }, false, 'equipment/closeWorkOrderDetail'),

      // 故障代码
      failureCodes: { symptoms: [], causes: [], actions: [] },
      failureCodeLoading: false,
      setFailureCodes: (type, codes) => set(
        (state) => ({ failureCodes: { ...state.failureCodes, [type]: codes } }),
        false,
        'equipment/setFailureCodes',
      ),
      setFailureCodeLoading: (loading) => set({ failureCodeLoading: loading }, false, 'equipment/setFailureCodeLoading'),
      failureCodeDrawerOpen: false,
      failureCodeDrawerType: 'symptoms',
      editingFailureCode: null,
      openFailureCodeDrawer: (type, code) => set({
        failureCodeDrawerOpen: true,
        failureCodeDrawerType: type,
        editingFailureCode: code || null,
      }, false, 'equipment/openFailureCodeDrawer'),
      closeFailureCodeDrawer: () => set({
        failureCodeDrawerOpen: false,
        editingFailureCode: null,
      }, false, 'equipment/closeFailureCodeDrawer'),

      // 校准计划
      calibrationPlans: [],
      calibrationPlanTotal: 0,
      calibrationPlanPage: 1,
      calibrationPlanPageSize: 20,
      calibrationPlanLoading: false,
      calibrationPlanStatusFilter: '',
      setCalibrationPlans: (plans) => set({ calibrationPlans: plans }, false, 'equipment/setCalibrationPlans'),
      setCalibrationPlanTotal: (total) => set({ calibrationPlanTotal: total }, false, 'equipment/setCalibrationPlanTotal'),
      setCalibrationPlanPage: (page) => set({ calibrationPlanPage: page }, false, 'equipment/setCalibrationPlanPage'),
      setCalibrationPlanPageSize: (size) => set({ calibrationPlanPageSize: size, calibrationPlanPage: 1 }, false, 'equipment/setCalibrationPlanPageSize'),
      setCalibrationPlanLoading: (loading) => set({ calibrationPlanLoading: loading }, false, 'equipment/setCalibrationPlanLoading'),
      setCalibrationPlanStatusFilter: (status) => set({ calibrationPlanStatusFilter: status, calibrationPlanPage: 1 }, false, 'equipment/setCalibrationPlanStatusFilter'),
      calibrationPlanDrawerOpen: false,
      editingCalibrationPlan: null,
      openCalibrationPlanDrawer: (plan) => set({
        calibrationPlanDrawerOpen: true,
        editingCalibrationPlan: plan || null,
      }, false, 'equipment/openCalibrationPlanDrawer'),
      closeCalibrationPlanDrawer: () => set({
        calibrationPlanDrawerOpen: false,
        editingCalibrationPlan: null,
      }, false, 'equipment/closeCalibrationPlanDrawer'),

      // 校准记录
      calibrationRecords: [],
      calibrationRecordTotal: 0,
      calibrationRecordPage: 1,
      calibrationRecordPageSize: 20,
      calibrationRecordLoading: false,
      setCalibrationRecords: (records) => set({ calibrationRecords: records }, false, 'equipment/setCalibrationRecords'),
      setCalibrationRecordTotal: (total) => set({ calibrationRecordTotal: total }, false, 'equipment/setCalibrationRecordTotal'),
      setCalibrationRecordPage: (page) => set({ calibrationRecordPage: page }, false, 'equipment/setCalibrationRecordPage'),
      setCalibrationRecordPageSize: (size) => set({ calibrationRecordPageSize: size, calibrationRecordPage: 1 }, false, 'equipment/setCalibrationRecordPageSize'),
      setCalibrationRecordLoading: (loading) => set({ calibrationRecordLoading: loading }, false, 'equipment/setCalibrationRecordLoading'),
      calibrationRecordDrawerOpen: false,
      editingCalibrationRecord: null,
      openCalibrationRecordDrawer: (record) => set({
        calibrationRecordDrawerOpen: true,
        editingCalibrationRecord: record || null,
      }, false, 'equipment/openCalibrationRecordDrawer'),
      closeCalibrationRecordDrawer: () => set({
        calibrationRecordDrawerOpen: false,
        editingCalibrationRecord: null,
      }, false, 'equipment/closeCalibrationRecordDrawer'),

      // ========== 备件管理 ==========
      spareParts: [],
      sparePartTotal: 0,
      sparePartPage: 1,
      sparePartPageSize: 20,
      sparePartLoading: false,
      sparePartKeyword: '',
      stockWarnings: [],
      stockWarningsLoading: false,
      setSpareParts: (parts) => set({ spareParts: parts }, false, 'equipment/setSpareParts'),
      setSparePartTotal: (total) => set({ sparePartTotal: total }, false, 'equipment/setSparePartTotal'),
      setSparePartPage: (page) => set({ sparePartPage: page }, false, 'equipment/setSparePartPage'),
      setSparePartPageSize: (size) => set({ sparePartPageSize: size, sparePartPage: 1 }, false, 'equipment/setSparePartPageSize'),
      setSparePartLoading: (loading) => set({ sparePartLoading: loading }, false, 'equipment/setSparePartLoading'),
      setSparePartKeyword: (keyword) => set({ sparePartKeyword: keyword, sparePartPage: 1 }, false, 'equipment/setSparePartKeyword'),
      setStockWarnings: (warnings) => set({ stockWarnings: warnings }, false, 'equipment/setStockWarnings'),
      setStockWarningsLoading: (loading) => set({ stockWarningsLoading: loading }, false, 'equipment/setStockWarningsLoading'),
      sparePartDrawerOpen: false,
      editingSparePart: null,
      openSparePartDrawer: (part) => set({
        sparePartDrawerOpen: true,
        editingSparePart: part || null,
      }, false, 'equipment/openSparePartDrawer'),
      closeSparePartDrawer: () => set({
        sparePartDrawerOpen: false,
        editingSparePart: null,
      }, false, 'equipment/closeSparePartDrawer'),
      stockInboundDrawerOpen: false,
      stockInboundSparePartId: null,
      openStockInboundDrawer: (sparePartId) => set({
        stockInboundDrawerOpen: true,
        stockInboundSparePartId: sparePartId,
      }, false, 'equipment/openStockInboundDrawer'),
      closeStockInboundDrawer: () => set({
        stockInboundDrawerOpen: false,
        stockInboundSparePartId: null,
      }, false, 'equipment/closeStockInboundDrawer'),

      // ========== 维护计划 ==========
      maintenancePlans: [],
      maintenancePlanTotal: 0,
      maintenancePlanPage: 1,
      maintenancePlanPageSize: 20,
      maintenancePlanLoading: false,
      maintenancePlanStatusFilter: '',
      maintenancePlanKeyword: '',
      setMaintenancePlans: (plans) => set({ maintenancePlans: plans }, false, 'equipment/setMaintenancePlans'),
      setMaintenancePlanTotal: (total) => set({ maintenancePlanTotal: total }, false, 'equipment/setMaintenancePlanTotal'),
      setMaintenancePlanPage: (page) => set({ maintenancePlanPage: page }, false, 'equipment/setMaintenancePlanPage'),
      setMaintenancePlanPageSize: (size) => set({ maintenancePlanPageSize: size, maintenancePlanPage: 1 }, false, 'equipment/setMaintenancePlanPageSize'),
      setMaintenancePlanLoading: (loading) => set({ maintenancePlanLoading: loading }, false, 'equipment/setMaintenancePlanLoading'),
      setMaintenancePlanStatusFilter: (status) => set({ maintenancePlanStatusFilter: status, maintenancePlanPage: 1 }, false, 'equipment/setMaintenancePlanStatusFilter'),
      setMaintenancePlanKeyword: (keyword) => set({ maintenancePlanKeyword: keyword, maintenancePlanPage: 1 }, false, 'equipment/setMaintenancePlanKeyword'),
      maintenancePlanDrawerOpen: false,
      editingMaintenancePlan: null,
      openMaintenancePlanDrawer: (plan) => set({
        maintenancePlanDrawerOpen: true,
        editingMaintenancePlan: plan || null,
      }, false, 'equipment/openMaintenancePlanDrawer'),
      closeMaintenancePlanDrawer: () => set({
        maintenancePlanDrawerOpen: false,
        editingMaintenancePlan: null,
      }, false, 'equipment/closeMaintenancePlanDrawer'),

      // ========== 巡检模板 ==========
      inspectionTemplates: [],
      inspectionTemplateTotal: 0,
      inspectionTemplatePage: 1,
      inspectionTemplatePageSize: 20,
      inspectionTemplateLoading: false,
      inspectionTemplateKeyword: '',
      setInspectionTemplates: (templates) => set({ inspectionTemplates: templates }, false, 'equipment/setInspectionTemplates'),
      setInspectionTemplateTotal: (total) => set({ inspectionTemplateTotal: total }, false, 'equipment/setInspectionTemplateTotal'),
      setInspectionTemplatePage: (page) => set({ inspectionTemplatePage: page }, false, 'equipment/setInspectionTemplatePage'),
      setInspectionTemplatePageSize: (size) => set({ inspectionTemplatePageSize: size, inspectionTemplatePage: 1 }, false, 'equipment/setInspectionTemplatePageSize'),
      setInspectionTemplateLoading: (loading) => set({ inspectionTemplateLoading: loading }, false, 'equipment/setInspectionTemplateLoading'),
      setInspectionTemplateKeyword: (keyword) => set({ inspectionTemplateKeyword: keyword, inspectionTemplatePage: 1 }, false, 'equipment/setInspectionTemplateKeyword'),
      inspectionTemplateDrawerOpen: false,
      editingInspectionTemplate: null,
      openInspectionTemplateDrawer: (template) => set({
        inspectionTemplateDrawerOpen: true,
        editingInspectionTemplate: template || null,
      }, false, 'equipment/openInspectionTemplateDrawer'),
      closeInspectionTemplateDrawer: () => set({
        inspectionTemplateDrawerOpen: false,
        editingInspectionTemplate: null,
      }, false, 'equipment/closeInspectionTemplateDrawer'),
      inspectionItemDrawerOpen: false,
      inspectionItemTemplateId: null,
      editingInspectionItem: null,
      openInspectionItemDrawer: (templateId, item) => set({
        inspectionItemDrawerOpen: true,
        inspectionItemTemplateId: templateId,
        editingInspectionItem: item || null,
      }, false, 'equipment/openInspectionItemDrawer'),
      closeInspectionItemDrawer: () => set({
        inspectionItemDrawerOpen: false,
        inspectionItemTemplateId: null,
        editingInspectionItem: null,
      }, false, 'equipment/closeInspectionItemDrawer'),

      // ========== 巡检完成 ==========
      inspectionCompleteDrawerOpen: false,
      completingWorkOrderId: null,
      completingTemplateName: null,
      completingTemplateItems: [],
      openInspectionCompleteDrawer: (workOrderId, templateName, items) => set({
        inspectionCompleteDrawerOpen: true,
        completingWorkOrderId: workOrderId,
        completingTemplateName: templateName,
        completingTemplateItems: items,
      }, false, 'equipment/openInspectionCompleteDrawer'),
      closeInspectionCompleteDrawer: () => set({
        inspectionCompleteDrawerOpen: false,
        completingWorkOrderId: null,
        completingTemplateName: null,
        completingTemplateItems: [],
      }, false, 'equipment/closeInspectionCompleteDrawer'),

      // ========== 报修抽屉 ==========
      repairDrawerOpen: false,
      repairEquipmentId: null,
      openRepairDrawer: (equipmentId) => set({
        repairDrawerOpen: true,
        repairEquipmentId: equipmentId,
      }, false, 'equipment/openRepairDrawer'),
      closeRepairDrawer: () => set({
        repairDrawerOpen: false,
        repairEquipmentId: null,
      }, false, 'equipment/closeRepairDrawer'),

      // ========== 超时配置 ==========
      claimTimeoutConfig: { emergency: 15, high: 30, medium: 60, low: 120 },
      setClaimTimeoutConfig: (config) => set({ claimTimeoutConfig: config }, false, 'equipment/setClaimTimeoutConfig'),

      // ========== 维修人员 ==========
      maintainers: [],
      setMaintainers: (maintainers) => set({ maintainers }, false, 'equipment/setMaintainers'),
    }),
    { name: 'equipment-store' },
  ),
)
