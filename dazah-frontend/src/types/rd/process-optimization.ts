// 工艺优化模块类型定义

export type OptimizationStatus = 'planning' | 'in_progress' | 'completed' | 'failed'

// 工作流阶段
export type OptimizationModule = 'doe' | 'impurity' | 'crystal' | 'quality' | 'lab_confirmation' | 'scaleup' | 'report'

export const OPTIMIZATION_MODULES: { key: OptimizationModule; label: string; icon: string }[] = [
  { key: 'doe', label: 'DOE实验设计', icon: 'ExperimentOutlined' },
  { key: 'impurity', label: '杂质研究', icon: 'BugOutlined' },
  { key: 'crystal', label: '晶型研究', icon: 'ApartmentOutlined' },
  { key: 'quality', label: '质量标准', icon: 'SafetyCertificateOutlined' },
  { key: 'scaleup', label: '公斤级放大', icon: 'ExpandOutlined' },
  { key: 'report', label: '报告生成', icon: 'FileDoneOutlined' },
]

// ============ DOE 相关类型 ============

export type DOEDesignType = 'orthogonal' | 'response_surface' | 'plackett_burman' | 'custom'

export interface DOEFactor {
  name: string
  symbol: string
  type: 'categorical' | 'numeric'
  levels: string[] | { lower: number; upper: number; steps?: number }
  unit?: string
}

export interface DOEResponse {
  name: string
  unit: string
  target: 'maximize' | 'minimize' | 'target_value'
  target_value?: number
  weight: number
}

export interface DOERun {
  run_no: number
  factor_values: Record<string, string | number>
  response_values: Record<string, number>
  status: 'planned' | 'completed' | 'failed'
  notes?: string
}

export interface AnovaRow {
  source: string
  df: number
  sum_of_squares: number
  mean_square: number
  f_value: number
  p_value: number
  significance: string
}

// ============ CPP评估相关类型 ============

export interface CPPControlRange {
  min: number
  max: number
  unit?: string
  justification: string
}

export interface CPPAssessment {
  critical_parameters: string[]
  control_ranges: Record<string, CPPControlRange>
  justification: string
  assessment_date?: string
}

// ============ 反应步骤优化相关类型 ============

export interface ReactionStep {
  id: string
  step_name: string
  step_order: number
  description?: string
  doe_experiment?: DOEExperiment
  status: 'pending' | 'in_progress' | 'completed'
}

export interface DOEAnalysisResult {
  anova_table: AnovaRow[]
  regression_model: string
  r_squared: number
  adjusted_r_squared: number
  optimal_conditions: Record<string, number>
  predicted_response: Record<string, number>
  significant_factors: string[]
  cpp_assessment?: CPPAssessment
}

export interface DOEExperiment {
  id: string
  design_type: DOEDesignType
  factors: DOEFactor[]
  responses: DOEResponse[]
  runs: DOERun[]
  analysis_result?: DOEAnalysisResult
  conclusion?: string
}

// ============ 杂质研究相关类型 ============

export type ImpurityCategory = 'process' | 'degradation' | 'residual_solvent' | 'elemental' | 'genotoxic'
export type ICHM7Class = 'class1' | 'class2' | 'class3' | 'class4' | 'class5'
export type ICHSolventClass = 'class1' | 'class2' | 'class3'
export type ControlMethod = 'process_control' | 'release_test' | 'both'

export interface Impurity {
  id: string
  name: string
  category: ImpurityCategory
  structure?: string
  source: string
  ich_m7_class?: ICHM7Class
  ich_solvent_class?: ICHSolventClass
  limit_ppm?: number
  typical_level_pct?: number
  control_method: ControlMethod
  detection_method?: string
  risk_level: 'low' | 'medium' | 'high'
  notes?: string
}

export interface ImpurityStudy {
  id: string
  impurities: Impurity[]
  control_strategy_summary?: string
  total_impurities_pct?: number
  max_single_impurity_pct?: number
  conclusion?: string
}

// ============ 晶型研究相关类型 ============

export type CrystalFormType = 'polymorph' | 'hydrate' | 'solvate' | 'salt' | 'amorphous'

export interface CrystalFormRecord {
  id: string
  form_name: string
  form_type: CrystalFormType
  solvent_system: string
  temperature_condition: string
  cooling_rate?: string
  crystallization_method: string
  xrd_peaks?: string
  stability_assessment?: string
  is_preferred: boolean
  notes?: string
}

export interface CrystalFormStudy {
  id: string
  records: CrystalFormRecord[]
  preferred_form?: CrystalFormRecord
  salt_screening_results?: string
  conclusion?: string
}

// ============ 质量标准相关类型 ============

export type TestMethod = 'hplc' | 'gc' | 'kf' | 'particle_size' | 'melting_point' | 'xrd' | 'titration' | 'ph' | 'visual' | 'other'

export interface QualityStandard {
  id: string
  test_item: string
  test_method: TestMethod
  method_reference?: string
  specification: string
  justification?: string
  category: 'identity' | 'assay' | 'impurity' | 'physical' | 'residual' | 'other'
}

export interface QualityStandardSet {
  id: string
  standards: QualityStandard[]
  shelf_life_proposal?: string
  storage_condition?: string
  packaging?: string
  conclusion?: string
}

// ============ 公斤级放大相关类型 ============

export interface ScaleUpBatch {
  id: string
  batch_no: string
  scale_kg: number
  date: string
  operator: string
  equipment: string
  parameters: Record<string, string | number>
  yield_pct: number
  purity_pct: number
  impurities_pct?: number
  appearance?: string
  comparison_notes?: string
  status: 'planned' | 'in_progress' | 'completed' | 'failed'
}

// ============ 小试工艺确认相关类型 ============

export interface LabConfirmationBatch {
  id: string
  batch_no: string
  scale_g: number
  date: string
  operator: string
  equipment: string
  parameters: Record<string, string | number>
  yield_pct: number
  purity_pct: number
  impurities_pct: number
  appearance: string
  observations?: string
  status: 'planned' | 'in_progress' | 'completed' | 'failed'
}

export interface LabConfirmationStudy {
  id: string
  purpose: string  // 小试确认目的
  batch: LabConfirmationBatch  // 单批小试确认
  conclusion: string  // 小试确认结论（作为放大方案依据）
}

export interface ScaleUpStudy {
  id: string
  target_scale_kg: number
  lab_confirmation_study_id?: string  // 关联的小试确认批ID
  material_balance?: string
  equipment_selection?: string
  parameter_adjustments?: string
  batch?: ScaleUpBatch  // 公斤级放大试验（单批）
  comparison_summary?: string  // 与小试的关键指标对比
  conclusion?: string
}

// ============ 工艺优化主记录 ============

export interface ProcessOptimization {
  id: string
  project_id: string
  optimization_no: string
  name: string
  source_route_id?: string
  source_route_name?: string
  description: string
  status: OptimizationStatus
  current_module: OptimizationModule
  doe_experiment?: DOEExperiment
  reaction_steps?: ReactionStep[]
  impurity_study?: ImpurityStudy
  crystal_form_study?: CrystalFormStudy
  quality_standard_set?: QualityStandardSet
  lab_confirmation_study?: LabConfirmationStudy
  scale_up_study?: ScaleUpStudy
  start_date: string | null
  end_date: string | null
  created_at: string
  updated_at: string
  created_by: string | null
}

// ============ API 请求/响应类型 ============

export interface OptimizationFilters {
  project_id?: string
  status?: OptimizationStatus | ''
  current_module?: OptimizationModule | ''
  keyword?: string
  page?: number
  page_size?: number
}

export interface OptimizationListResponse {
  items: ProcessOptimization[]
  total: number
  page: number
  page_size: number
}

export interface OptimizationCreate {
  project_id: string
  name: string
  source_route_id?: string
  source_route_name?: string
  description?: string
}

export interface OptimizationUpdate {
  name?: string
  description?: string
  status?: OptimizationStatus
  current_module?: OptimizationModule
  doe_experiment?: DOEExperiment
  reaction_steps?: ReactionStep[]
  impurity_study?: ImpurityStudy
  crystal_form_study?: CrystalFormStudy
  quality_standard_set?: QualityStandardSet
  lab_confirmation_study?: LabConfirmationStudy
  scale_up_study?: ScaleUpStudy
  end_date?: string
}
