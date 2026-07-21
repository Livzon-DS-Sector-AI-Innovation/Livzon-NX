// 打通路线模块类型定义

export type RouteStatus = 'planning' | 'in_progress' | 'completed' | 'failed'
export type AssessmentLevel = 'low' | 'medium' | 'high' | 'critical'

// 工作流阶段
export type WorkflowModule = 'research' | 'trial' | 'assessment' | 'confirmation'

export const WORKFLOW_MODULES: { key: WorkflowModule; label: string; icon: string }[] = [
  { key: 'research', label: '文献解析+路线提取', icon: 'FilePdfOutlined' },
  { key: 'trial', label: '路线尝试+数据录入', icon: 'ExperimentOutlined' },
  { key: 'assessment', label: '四维度评估', icon: 'DashboardOutlined' },
  { key: 'confirmation', label: '路线确认+报告生成', icon: 'FileDoneOutlined' },
]

// 文献来源
export interface LiteratureSource {
  id: string
  type: 'pdf' | 'doi' | 'pmid' | 'manual'
  title: string
  file_path?: string
  doi?: string
  pmid?: string
  pages?: string
}

// 候选路线（从文献中提取）
export interface CandidateRoute {
  id: string
  name: string
  steps: number
  total_yield: number
  starting_materials: string[]
  key_step: string
  advantages: string[]
  risks: string[]
  is_recommended: boolean
  description?: string
  '文献页码'?: string
  '反应条件'?: string
  smiles?: string
  literature_id?: string
}

// 实验方案（Module 1 产出）
export interface ExperimentPlan {
  route_id: string
  route_name: string
  // 实验步骤
  steps: {
    step_no: number
    description: string
    reagents: string[]
    conditions: string
    expected_yield: number
    duration: string
    notes?: string
  }[]
  // 分析方法
  analysis_methods: {
    name: string
    purpose: string
    method: string
    equipment: string
  }[]
  // 物料清单
  materials: {
    name: string
    cas_number?: string
    quantity: string
    supplier?: string
    purity?: string
    storage?: string
    lead_time?: string
  }[]
  // 设备需求
  equipment: string[]
  // 安全注意事项
  safety_notes: string[]
  // 预计周期
  estimated_duration: string
}

// 四维度评估（含动态权重）
export interface DimensionWeights {
  safety: number
  environmental: number
  cost: number
  feasibility: number
}

export interface DimensionScore {
  safety: number
  environmental: number
  cost: number
  feasibility: number
}

export interface DimensionAssessment {
  weights: DimensionWeights
  scores: DimensionScore
  weighted_total: number
  notes: {
    safety: string
    environmental: string
    cost: string
    feasibility: string
  }
}

// 实验记录
export interface ExperimentRecord {
  id: string
  route_id: string
  experiment_no: string
  title: string
  description: string
  date: string
  operator: string
  status: 'planned' | 'in_progress' | 'completed' | 'failed'
  reaction_temp?: string
  reaction_time?: string
  yield?: number
  purity?: number
  impurities?: string
  result_summary: string | null
  created_at: string
  updated_at: string
}

// 打通路线（含工作流状态）
export interface RouteDevelopment {
  id: string
  project_id: string
  route_no: string
  name: string
  source: string
  source_reference: string | null
  description: string
  status: RouteStatus
  current_module: WorkflowModule
  literature_sources: LiteratureSource[]
  candidate_routes: CandidateRoute[]
  selected_route_ids: string[]
  experiment_plans: ExperimentPlan[]  // Module 1 产出
  experiments: ExperimentRecord[]
  assessment: DimensionAssessment | null
  deliverables: RouteDeliverable[]
  start_date: string | null
  end_date: string | null
  created_at: string
  updated_at: string
  created_by: string | null
}

// 产出物
export interface RouteDeliverable {
  id: string
  route_id: string
  type: 'route_confirmation' | 'safety_assessment' | 'impurity_analysis' | 'scale_up_summary'
  name: string
  file_path: string | null
  upload_date: string
  uploaded_by: string | null
}

// 筛选条件
export interface RouteFilters {
  project_id?: string
  status?: RouteStatus | ''
  current_module?: WorkflowModule | ''
  keyword?: string
  page?: number
  page_size?: number
}

// 列表响应
export interface RouteListResponse {
  items: RouteDevelopment[]
  total: number
  page: number
  page_size: number
}

// 创建请求
export interface RouteCreate {
  project_id: string
  route_no?: string
  name: string
  source: string
  source_reference?: string
  description?: string
}

// 更新请求
export interface RouteUpdate {
  route_no?: string
  name?: string
  source?: string
  source_reference?: string
  description?: string
  status?: RouteStatus
  current_module?: WorkflowModule
  literature_sources?: LiteratureSource[]
  candidate_routes?: CandidateRoute[]
  selected_route_ids?: string[]
  experiment_plans?: ExperimentPlan[]
  experiments?: ExperimentRecord[]
  assessment?: DimensionAssessment
  end_date?: string
}
