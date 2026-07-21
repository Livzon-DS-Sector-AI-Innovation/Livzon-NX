import { create } from 'zustand'
import { devtools } from 'zustand/middleware'
import {
  ProcessOptimization,
  OptimizationStatus,
  OptimizationModule,
} from '@/types/rd'

interface ProcessOptimizationStore {
  // 数据
  optimizations: ProcessOptimization[]
  total: number
  loading: boolean

  // 当前选中的优化记录
  currentOptimization: ProcessOptimization | null

  // 当前工作流模块
  currentModule: OptimizationModule

  // 筛选状态
  statusFilter: OptimizationStatus | ''
  moduleFilter: OptimizationModule | ''
  keyword: string
  page: number
  pageSize: number

  // 抽屉状态
  drawerOpen: boolean
  editingOptimization: ProcessOptimization | null

  // 操作
  setOptimizations: (optimizations: ProcessOptimization[]) => void
  setTotal: (total: number) => void
  setLoading: (loading: boolean) => void
  setCurrentOptimization: (optimization: ProcessOptimization | null) => void
  setCurrentModule: (module: OptimizationModule) => void
  setStatusFilter: (status: OptimizationStatus | '') => void
  setModuleFilter: (module: OptimizationModule | '') => void
  setKeyword: (keyword: string) => void
  setPage: (page: number) => void
  setPageSize: (pageSize: number) => void
  resetFilters: () => void
  openDrawer: (optimization?: ProcessOptimization) => void
  closeDrawer: () => void
  updateCurrentOptimization: (updates: Partial<ProcessOptimization>) => void
}

export const useProcessOptimizationStore = create<ProcessOptimizationStore>()(
  devtools(
    (set, get) => ({
      optimizations: [],
      total: 0,
      loading: false,

      currentOptimization: null,
      currentModule: 'doe',

      statusFilter: '',
      moduleFilter: '',
      keyword: '',
      page: 1,
      pageSize: 20,

      drawerOpen: false,
      editingOptimization: null,

      setOptimizations: (optimizations) => set({ optimizations }),
      setTotal: (total) => set({ total }),
      setLoading: (loading) => set({ loading }),
      setCurrentOptimization: (currentOptimization) => set({ currentOptimization }),
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
      openDrawer: (optimization) =>
        set({ drawerOpen: true, editingOptimization: optimization || null }),
      closeDrawer: () =>
        set({ drawerOpen: false, editingOptimization: null }),
      updateCurrentOptimization: (updates) => {
        const { currentOptimization } = get()
        if (currentOptimization) {
          const updated = { ...currentOptimization, ...updates }
          set({ currentOptimization: updated })
        }
      },
    }),
    { name: 'process-optimization-store' }
  )
)
