import { create } from 'zustand'
import { devtools } from 'zustand/middleware'
import {
  ResearchProject,
  ResearchProjectStage,
  ResearchProjectStatus,
} from '@/types/rd'

interface ResearchStore {
  // 数据
  projects: ResearchProject[]
  total: number
  loading: boolean

  // 筛选状态
  stageFilter: ResearchProjectStage | ''
  statusFilter: ResearchProjectStatus | ''
  keyword: string
  page: number
  pageSize: number

  // 抽屉状态
  drawerOpen: boolean
  editingProject: ResearchProject | null

  // 操作
  setProjects: (projects: ResearchProject[]) => void
  setTotal: (total: number) => void
  setLoading: (loading: boolean) => void
  setStageFilter: (stage: ResearchProjectStage | '') => void
  setStatusFilter: (status: ResearchProjectStatus | '') => void
  setKeyword: (keyword: string) => void
  setPage: (page: number) => void
  setPageSize: (pageSize: number) => void
  resetFilters: () => void
  openDrawer: (project?: ResearchProject) => void
  closeDrawer: () => void
}

export const useResearchStore = create<ResearchStore>()(
  devtools(
    (set) => ({
      projects: [],
      total: 0,
      loading: false,

      stageFilter: '',
      statusFilter: '',
      keyword: '',
      page: 1,
      pageSize: 20,

      drawerOpen: false,
      editingProject: null,

      setProjects: (projects) => set({ projects }),
      setTotal: (total) => set({ total }),
      setLoading: (loading) => set({ loading }),
      setStageFilter: (stageFilter) => set({ stageFilter, page: 1 }),
      setStatusFilter: (statusFilter) => set({ statusFilter, page: 1 }),
      setKeyword: (keyword) => set({ keyword, page: 1 }),
      setPage: (page) => set({ page }),
      setPageSize: (pageSize) => set({ pageSize, page: 1 }),
      resetFilters: () =>
        set({
          stageFilter: '',
          statusFilter: '',
          keyword: '',
          page: 1,
          pageSize: 20,
        }),
      openDrawer: (project) =>
        set({ drawerOpen: true, editingProject: project || null }),
      closeDrawer: () =>
        set({ drawerOpen: false, editingProject: null }),
    }),
    { name: 'research-store' }
  )
)
