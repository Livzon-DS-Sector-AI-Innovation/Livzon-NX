import { create } from 'zustand'
import { devtools } from 'zustand/middleware'
import {
  DeviationListItem,
  DeviationDetail,
  DeviationStatus,
  DeviationLevel,
  CapaDetail,
  CapaWorkflowStatus,
  CapaSource,
  CapaCategory,
  DepartmentContact,
  FeishuCapaLedgerItem,
} from '@/types/quality'

// ============ Deviation Store ============
interface DeviationStore {
  // 数据
  deviations: DeviationListItem[]
  total: number
  loading: boolean

  // 筛选状态
  statusFilter: DeviationStatus | ''
  levelFilter: DeviationLevel | ''
  departmentFilter: string | ''
  keyword: string
  deviationCodeFilter: string
  productKeywordFilter: string
  hasOccurredBeforeFilter: '' | 'true' | 'false'
  isClosedFilter: '' | 'true' | 'false'
  investigationCompletedFrom: string
  investigationCompletedTo: string
  rootCauseKeywordFilter: string
  correctiveActionsKeywordFilter: string
  page: number
  pageSize: number

  // 操作
  setDeviations: (deviations: DeviationListItem[]) => void
  setTotal: (total: number) => void
  setLoading: (loading: boolean) => void
  setStatusFilter: (status: DeviationStatus | '') => void
  setLevelFilter: (level: DeviationLevel | '') => void
  setDepartmentFilter: (department: string | '') => void
  setKeyword: (keyword: string) => void
  setDeviationCodeFilter: (value: string) => void
  setProductKeywordFilter: (value: string) => void
  setHasOccurredBeforeFilter: (value: '' | 'true' | 'false') => void
  setIsClosedFilter: (value: '' | 'true' | 'false') => void
  setInvestigationCompletedRange: (from: string, to: string) => void
  setRootCauseKeywordFilter: (value: string) => void
  setCorrectiveActionsKeywordFilter: (value: string) => void
  setPage: (page: number) => void
  setPageSize: (pageSize: number) => void
  resetFilters: () => void
}

export const useDeviationStore = create<DeviationStore>()(
  devtools(
    (set) => ({
      deviations: [],
      total: 0,
      loading: false,

      statusFilter: '',
      levelFilter: '',
      departmentFilter: '',
      keyword: '',
      deviationCodeFilter: '',
      productKeywordFilter: '',
      hasOccurredBeforeFilter: '',
      isClosedFilter: '',
      investigationCompletedFrom: '',
      investigationCompletedTo: '',
      rootCauseKeywordFilter: '',
      correctiveActionsKeywordFilter: '',
      page: 1,
      pageSize: 20,

      setDeviations: (deviations) => set({ deviations }),
      setTotal: (total) => set({ total }),
      setLoading: (loading) => set({ loading }),
      setStatusFilter: (statusFilter) => set({ statusFilter, page: 1 }),
      setLevelFilter: (levelFilter) => set({ levelFilter, page: 1 }),
      setDepartmentFilter: (departmentFilter) => set({ departmentFilter, page: 1 }),
      setKeyword: (keyword) => set({ keyword, page: 1 }),
      setDeviationCodeFilter: (deviationCodeFilter) => set({ deviationCodeFilter, page: 1 }),
      setProductKeywordFilter: (productKeywordFilter) => set({ productKeywordFilter, page: 1 }),
      setHasOccurredBeforeFilter: (hasOccurredBeforeFilter) => set({ hasOccurredBeforeFilter, page: 1 }),
      setIsClosedFilter: (isClosedFilter) => set({ isClosedFilter, page: 1 }),
      setInvestigationCompletedRange: (investigationCompletedFrom, investigationCompletedTo) =>
        set({ investigationCompletedFrom, investigationCompletedTo, page: 1 }),
      setRootCauseKeywordFilter: (rootCauseKeywordFilter) => set({ rootCauseKeywordFilter, page: 1 }),
      setCorrectiveActionsKeywordFilter: (correctiveActionsKeywordFilter) =>
        set({ correctiveActionsKeywordFilter, page: 1 }),
      setPage: (page) => set({ page }),
      setPageSize: (pageSize) => set({ pageSize, page: 1 }),
      resetFilters: () =>
        set({
          statusFilter: '',
          levelFilter: '',
          departmentFilter: '',
          keyword: '',
          deviationCodeFilter: '',
          productKeywordFilter: '',
          hasOccurredBeforeFilter: '',
          isClosedFilter: '',
          investigationCompletedFrom: '',
          investigationCompletedTo: '',
          rootCauseKeywordFilter: '',
          correctiveActionsKeywordFilter: '',
          page: 1,
          pageSize: 20,
        }),
    }),
    { name: 'deviation-store' }
  )
)

// ============ CAPA Store ============
interface CapaStore {
  // 数据
  capas: FeishuCapaLedgerItem[]
  total: number
  loading: boolean

  // 筛选状态
  statusFilter: CapaWorkflowStatus | ''
  sourceFilter: CapaSource | ''
  categoryFilter: CapaCategory | ''
  keyword: string
  departmentFilter: string
  productFilter: string
  page: number
  pageSize: number

  // 操作
  setCapas: (capas: FeishuCapaLedgerItem[]) => void
  setTotal: (total: number) => void
  setLoading: (loading: boolean) => void
  setStatusFilter: (status: CapaWorkflowStatus | '') => void
  setSourceFilter: (source: CapaSource | '') => void
  setCategoryFilter: (category: CapaCategory | '') => void
  setKeyword: (keyword: string) => void
  setDepartmentFilter: (value: string) => void
  setProductFilter: (value: string) => void
  setPage: (page: number) => void
  setPageSize: (pageSize: number) => void
  resetFilters: () => void
}

export const useCapaStore = create<CapaStore>()(
  devtools(
    (set) => ({
      capas: [],
      total: 0,
      loading: false,

      statusFilter: '',
      sourceFilter: '',
      categoryFilter: '',
      keyword: '',
      departmentFilter: '',
      productFilter: '',
      page: 1,
      pageSize: 20,

      setCapas: (capas) => set({ capas }),
      setTotal: (total) => set({ total }),
      setLoading: (loading) => set({ loading }),
      setStatusFilter: (statusFilter) => set({ statusFilter, page: 1 }),
      setSourceFilter: (sourceFilter) => set({ sourceFilter, page: 1 }),
      setCategoryFilter: (categoryFilter) => set({ categoryFilter, page: 1 }),
      setKeyword: (keyword) => set({ keyword, page: 1 }),
      setDepartmentFilter: (departmentFilter) => set({ departmentFilter, page: 1 }),
      setProductFilter: (productFilter) => set({ productFilter, page: 1 }),
      setPage: (page) => set({ page }),
      setPageSize: (pageSize) => set({ pageSize, page: 1 }),
      resetFilters: () =>
        set({
          statusFilter: '',
          sourceFilter: '',
          categoryFilter: '',
          keyword: '',
          departmentFilter: '',
          productFilter: '',
          page: 1,
          pageSize: 20,
        }),
    }),
    { name: 'capa-store' }
  )
)

interface ChangeStore {
  changes: any[]
  total: number
  loading: boolean
  page: number
  pageSize: number
  changeCodeFilter: string
  applicantDepartmentFilter: string
  changeObjectFilter: string
  changeLevelFilter: string
  applicationDateFrom: string
  applicationDateTo: string
  plannedApprovalDateFrom: string
  plannedApprovalDateTo: string
  executionDateFrom: string
  executionDateTo: string
  closureDateFrom: string
  closureDateTo: string
  contentKeywordFilter: string
  setChanges: (changes: any[]) => void
  setTotal: (total: number) => void
  setLoading: (loading: boolean) => void
  setPage: (page: number) => void
  setPageSize: (pageSize: number) => void
  setChangeCodeFilter: (value: string) => void
  setApplicantDepartmentFilter: (value: string) => void
  setChangeObjectFilter: (value: string) => void
  setChangeLevelFilter: (value: string) => void
  setApplicationDateRange: (from: string, to: string) => void
  setPlannedApprovalDateRange: (from: string, to: string) => void
  setExecutionDateRange: (from: string, to: string) => void
  setClosureDateRange: (from: string, to: string) => void
  setContentKeywordFilter: (value: string) => void
  resetFilters: () => void
}

export const useChangeStore = create<ChangeStore>()(
  devtools(
    (set) => ({
      changes: [],
      total: 0,
      loading: false,
      page: 1,
      pageSize: 20,
      changeCodeFilter: '',
      applicantDepartmentFilter: '',
      changeObjectFilter: '',
      changeLevelFilter: '',
      applicationDateFrom: '',
      applicationDateTo: '',
      plannedApprovalDateFrom: '',
      plannedApprovalDateTo: '',
      executionDateFrom: '',
      executionDateTo: '',
      closureDateFrom: '',
      closureDateTo: '',
      contentKeywordFilter: '',
      setChanges: (changes) => set({ changes }),
      setTotal: (total) => set({ total }),
      setLoading: (loading) => set({ loading }),
      setPage: (page) => set({ page }),
      setPageSize: (pageSize) => set({ pageSize, page: 1 }),
      setChangeCodeFilter: (changeCodeFilter) => set({ changeCodeFilter, page: 1 }),
      setApplicantDepartmentFilter: (applicantDepartmentFilter) =>
        set({ applicantDepartmentFilter, page: 1 }),
      setChangeObjectFilter: (changeObjectFilter) => set({ changeObjectFilter, page: 1 }),
      setChangeLevelFilter: (changeLevelFilter) => set({ changeLevelFilter, page: 1 }),
      setApplicationDateRange: (applicationDateFrom, applicationDateTo) =>
        set({ applicationDateFrom, applicationDateTo, page: 1 }),
      setPlannedApprovalDateRange: (plannedApprovalDateFrom, plannedApprovalDateTo) =>
        set({ plannedApprovalDateFrom, plannedApprovalDateTo, page: 1 }),
      setExecutionDateRange: (executionDateFrom, executionDateTo) =>
        set({ executionDateFrom, executionDateTo, page: 1 }),
      setClosureDateRange: (closureDateFrom, closureDateTo) =>
        set({ closureDateFrom, closureDateTo, page: 1 }),
      setContentKeywordFilter: (contentKeywordFilter) => set({ contentKeywordFilter, page: 1 }),
      resetFilters: () =>
        set({
          changeCodeFilter: '',
          applicantDepartmentFilter: '',
          changeObjectFilter: '',
          changeLevelFilter: '',
          applicationDateFrom: '',
          applicationDateTo: '',
          plannedApprovalDateFrom: '',
          plannedApprovalDateTo: '',
          executionDateFrom: '',
          executionDateTo: '',
          closureDateFrom: '',
          closureDateTo: '',
          contentKeywordFilter: '',
          page: 1,
          pageSize: 20,
        }),
    }),
    { name: 'change-store' }
  )
)

// ============ Department Contact Store ============
interface DepartmentContactStore {
  // 数据
  contacts: DepartmentContact[]
  total: number
  loading: boolean

  // 分页
  page: number
  pageSize: number

  // 操作
  setContacts: (contacts: DepartmentContact[]) => void
  setTotal: (total: number) => void
  setLoading: (loading: boolean) => void
  setPage: (page: number) => void
  setPageSize: (pageSize: number) => void
}

export const useDepartmentContactStore = create<DepartmentContactStore>()(
  devtools(
    (set) => ({
      contacts: [],
      total: 0,
      loading: false,

      page: 1,
      pageSize: 20,

      setContacts: (contacts) => set({ contacts }),
      setTotal: (total) => set({ total }),
      setLoading: (loading) => set({ loading }),
      setPage: (page) => set({ page }),
      setPageSize: (pageSize) => set({ pageSize, page: 1 }),
    }),
    { name: 'department-contact-store' }
  )
)
