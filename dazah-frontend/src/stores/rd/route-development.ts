import { create } from 'zustand'
import { devtools } from 'zustand/middleware'
import {
  RouteDevelopment,
  RouteStatus,
  WorkflowModule,
  CandidateRoute,
  ExperimentRecord,
  DimensionAssessment,
  DimensionWeights,
  LiteratureSource,
} from '@/types/rd'

interface RouteDevelopmentStore {
  // 数据
  routes: RouteDevelopment[]
  total: number
  loading: boolean

  // 当前选中的路线
  currentRoute: RouteDevelopment | null

  // 当前工作流模块
  currentModule: WorkflowModule

  // 筛选状态
  statusFilter: RouteStatus | ''
  moduleFilter: WorkflowModule | ''
  keyword: string
  page: number
  pageSize: number

  // 抽屉状态
  drawerOpen: boolean
  editingRoute: RouteDevelopment | null

  // 操作
  setRoutes: (routes: RouteDevelopment[]) => void
  setTotal: (total: number) => void
  setLoading: (loading: boolean) => void
  setCurrentRoute: (route: RouteDevelopment | null) => void
  setCurrentModule: (module: WorkflowModule) => void
  setStatusFilter: (status: RouteStatus | '') => void
  setModuleFilter: (module: WorkflowModule | '') => void
  setKeyword: (keyword: string) => void
  setPage: (page: number) => void
  setPageSize: (pageSize: number) => void
  resetFilters: () => void
  openDrawer: (route?: RouteDevelopment) => void
  closeDrawer: () => void
  updateCurrentRoute: (updates: Partial<RouteDevelopment>) => void
}

export const useRouteDevelopmentStore = create<RouteDevelopmentStore>()(
  devtools(
    (set, get) => ({
      routes: [],
      total: 0,
      loading: false,

      currentRoute: null,
      currentModule: 'research',

      statusFilter: '',
      moduleFilter: '',
      keyword: '',
      page: 1,
      pageSize: 20,

      drawerOpen: false,
      editingRoute: null,

      setRoutes: (routes) => set({ routes }),
      setTotal: (total) => set({ total }),
      setLoading: (loading) => set({ loading }),
      setCurrentRoute: (currentRoute) => set({ currentRoute }),
      setCurrentModule: (currentModule) => set({ currentModule }),
      setStatusFilter: (statusFilter) => set({ statusFilter, page: 1 }),
      setModuleFilter: (moduleFilter) => set({ moduleFilter, page: 1 }),
      setKeyword: (keyword) => set({ keyword, page: 1 }),
      setPage: (page) => set({ page }),
      setPageSize: (pageSize) => set({ pageSize, page: 1 }),
      resetFilters: () =>
        set({
          statusFilter: '',
          moduleFilter: '',
          keyword: '',
          page: 1,
          pageSize: 20,
        }),
      openDrawer: (route) =>
        set({ drawerOpen: true, editingRoute: route || null }),
      closeDrawer: () =>
        set({ drawerOpen: false, editingRoute: null }),
      updateCurrentRoute: (updates) => {
        const { currentRoute } = get()
        if (currentRoute) {
          const updated = { ...currentRoute, ...updates }
          set({ currentRoute: updated })
        }
      },
    }),
    { name: 'route-development-store' }
  )
)
