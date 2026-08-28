import type { components } from '@/types/generated/schema'

export interface Employee {
  id: string
  employee_number: string
  seq_number?: number
  name: string
  domain_account?: string
  department: string
  sub_department?: string
  team?: string
  position: string
  job_category?: string
  level?: string
  employment_type?: string
  qualifications?: string[]
  qualification_type?: string
  certificate_number?: string
  certificate_review_date?: string
  gender?: string
  ethnic_group?: string
  native_place?: string
  political_status?: string
  marital_status?: string
  health_status?: string
  household_type?: string
  status_category?: string
  birth_year?: number
  birth_month?: number
  birth_day?: number
  age?: number
  work_start_date?: string
  factory_entry_date?: string
  livo_entry_date?: string
  hire_date: string
  graduation_date?: string
  work_years?: number
  factory_tenure?: string
  company_tenure?: string
  education?: string
  degree?: string
  classification?: string
  school?: string
  major?: string
  id_card?: string
  id_card_expiry?: string
  id_card_address?: string
  current_address?: string
  contract_type?: string
  contract_start_date?: string
  contract_end_date?: string
  contract_start_2?: string
  contract_end_2?: string
  contract_start_3?: string
  contract_end_3?: string
  contract_start_4?: string
  contract_end_4?: string
  contract_start_5?: string
  contract_end_5?: string
  contract_start_6?: string
  contract_end_6?: string
  contract_opinion?: string
  dept_leader_name?: string
  phone?: string
  email?: string
  emergency_contact_name?: string
  emergency_contact_phone?: string
  emergency_contact_relation?: string
  bank_account?: string
  training_id?: string
  archive_number?: string
  work_experience_1?: string
  work_experience_2?: string
  work_experience_3?: string
  work_experience_4?: string
  transfer_history?: string
  remarks?: string[]
  status: string
  probation_status?: string
  planned_probation_date?: string
  probation_effective_date?: string
  last_working_day?: string
  offboarding_type?: string
  offboarding_reason?: string
  feishu_record_id?: string
  feishu_synced_at?: string
  created_at?: string
  updated_at?: string
}

export type EmployeeCreateInput = components['schemas']['EmployeeCreate']
export type EmployeeUpdateInput = components['schemas']['EmployeeUpdate']

// TODO: 生成 schema 未包含响应包装类型，待后端 OpenAPI 补充后替换
export interface EmployeeListResponse {
  code: number
  message: string
  data: Employee[]
  meta?: {
    page: number
    page_size: number
    total: number
  }
}

// TODO: 生成 schema 未包含响应包装类型，待后端 OpenAPI 补充后替换
export interface EmployeeResponse {
  code: number
  message: string
  data: Employee
}

export interface EmployeeStats {
  total?: number
  status_distribution?: Record<string, number>
  department_distribution?: Array<{ department: string; count: number }>
  education_distribution?: Record<string, number>
  contract_expiring_count?: number
  contract_expiring_list?: Array<{
    employee_number: string
    name: string
    department: string | null
    position: string | null
    contract_end_date: string | null
  }>
}

// TODO: 生成 schema 未包含响应包装类型，待后端 OpenAPI 补充后替换
export interface SyncStatusResponse {
  code: number
  message: string
  data: {
    local_total: number
    feishu_total: number
    synced_count: number
    unsynced_count: number
    conflict_count: number
    last_sync_at: string | null
  }
}

export interface Department {
  id: string
  name: string
  code?: string
  description?: string
  leader_name?: string
  parent_id?: string
  feishu_open_department_id?: string
  sort_order?: number
  headcount?: number
  responsibilities?: string
  category?: string
  current_count?: number
  vacancy?: number
  children?: Department[]
  created_at?: string
  updated_at?: string
}

// ─── 部门 API 类型 (从 OpenAPI 生成的 schema) ───
// components imported at top

export type DepartmentCreateInput = components['schemas']['DepartmentCreate']
export type DepartmentUpdateInput = components['schemas']['DepartmentUpdate']

// ─── 部门 UI 类型 (ViewModel，基于 API 类型扩展) ───

// 部门分类枚举配置
export const DEPARTMENT_CATEGORIES = {
  quality: {
    label: '质量管理类',
    departments: ['QA部', 'QC部', '过程控制部IC'],
  },
  safety: {
    label: '安全管理类',
    departments: ['安全管理科', '应急消保队'],
  },
  workshop_201: {
    label: '201车间类',
    departments: ['201一车间', '201二车间', '201二车间（多拉）', '201三车间'],
  },
  production: {
    label: '生产管理类',
    departments: ['生产管理部', '仓储部'],
  },
} as const

export function getDepartmentCategory(deptName: string): string | null {
  for (const [key, value] of Object.entries(DEPARTMENT_CATEGORIES)) {
    if (value.departments.some(d => deptName.includes(d) || d.includes(deptName))) {
      return value.label
    }
  }
  return null
}

export interface OrgTreeNode {
  id: string
  name: string
  type: 'department' | 'employee'
  leader_name?: string | null
  current_count?: number | null
  headcount?: number | null
  vacancy?: number | null
  category?: string | null
  sort_order?: number | null
  children?: OrgTreeNode[]
}

// TODO: 生成 schema 未包含响应包装类型，待后端 OpenAPI 补充后替换
export interface DepartmentListResponse {
  code: number
  message: string
  data: Department[]
  meta?: {
    page: number
    page_size: number
    total: number
  }
}

export interface Team {
  id: string
  name: string
  code?: string
  description?: string
  department_id: string
  department?: Department
  created_at?: string
  updated_at?: string
}

export type TeamCreateInput = components['schemas']['TeamCreate']
export type TeamUpdateInput = components['schemas']['TeamUpdate']

// TODO: 生成 schema 未包含响应包装类型，待后端 OpenAPI 补充后替换
export interface TeamListResponse {
  code: number
  message: string
  data: Team[]
  meta?: {
    page: number
    page_size: number
    total: number
  }
}

export interface OffboardingRecord {
  id: string
  employee_id: string
  employee?: Employee
  // Core identifiers
  seq_number?: number
  employee_number?: string
  name?: string
  domain_account?: string
  // Personal info
  gender?: string
  ethnic_group?: string
  native_place?: string
  political_status?: string
  marital_status?: string
  health_status?: string
  household_type?: string
  status_category?: string
  // Birth date
  birth_year?: number
  birth_month?: number
  birth_day?: number
  age?: number
  // ID & address
  id_card?: string
  id_card_expiry?: string
  current_address?: string
  // Contact
  phone?: string
  email?: string
  emergency_contact_name?: string
  emergency_contact_phone?: string
  emergency_contact_relation?: string
  // Department & job
  department?: string
  sub_department?: string
  position?: string
  level?: string
  employment_type?: string
  probation_status?: string
  probation_effective_date?: string
  // Career dates
  hire_date?: string
  work_start_date?: string
  factory_entry_date?: string
  livo_entry_date?: string
  work_years?: string
  offboarding_date?: string
  // Offboarding specific
  offboarding_type: string
  reason?: string
  handover_status: string
  // Education
  education?: string
  degree?: string
  major?: string
  school?: string
  graduation_date?: string
  // Qualifications
  qualification_type?: string
  qualifications?: string[]
  certificate_number?: string
  certificate_review_date?: string
  // Contract
  contract_start_date?: string
  contract_end_date?: string
  contract_end_2?: string
  contract_end_3?: string
  contract_end_4?: string
  contract_end_5?: string
  contract_start_2?: string
  contract_start_3?: string
  contract_start_4?: string
  contract_start_5?: string
  contract_start_6?: string
  contract_end_6?: string
  // Work experience
  work_experience_1?: string
  work_experience_2?: string
  work_experience_3?: string
  work_experience_4?: string
  // Archive & notes
  archive_number?: string
  notes?: string
  // Feishu sync
  feishu_record_id?: string
  feishu_synced_at?: string
  created_at?: string
  updated_at?: string
}

export type OffboardingRecordCreateInput = components['schemas']['OffboardingRecordCreate']
export type OffboardingRecordUpdateInput = components['schemas']['OffboardingRecordUpdate']

// TODO: 生成 schema 未包含响应包装类型，待后端 OpenAPI 补充后替换
export interface OffboardingRecordListResponse {
  code: number
  message: string
  data: OffboardingRecord[]
  meta?: {
    page: number
    page_size: number
    total: number
  }
}

export interface OnboardingRecord {
  id?: string
  seq_number?: string | number | null
  employee_number?: string | null
  name?: string | null
  domain_account?: string | null
  department?: string | null
  team?: string | null
  position?: string | null
  job_category?: string | null
  status_category?: string | null
  is_employed?: string | boolean | null
  hire_date?: string | null
  factory_entry_date?: string | null
  livo_entry_date?: string | null
  work_start_date?: string | null
  graduation_date?: string | null
  birth_month?: string | number | null
  birth_day?: string | number | null
  age?: string | number | null
  work_years?: string | number | null
  factory_tenure?: string | number | null
  company_tenure?: string | number | null
  hire_month?: string | number | null
  education?: string | null
  school?: string | null
  major?: string | null
  classification?: string | null
  id_card?: string | null
  id_card_expiry?: string | null
  id_card_address?: string | null
  current_address?: string | null
  marital_status?: string | null
  household_type?: string | null
  political_status?: string | null
  phone?: string | null
  email?: string | null
  emergency_contact_phone?: string | null
  emergency_contact_relation?: string | null
  contract_type?: string | null
  contract_start_date?: string | null
  contract_end_date?: string | null
  contract_start_2?: string | null
  contract_end_2?: string | null
  contract_start_3?: string | null
  contract_end_3?: string | null
  contract_start_4?: string | null
  contract_end_4?: string | null
  bank_account?: string | null
  bank_account_location?: string | null
  training_id?: string | null
  transfer_history?: string | null
  remarks?: string[] | null
  feishu_synced_at?: string | null
}

export interface DepartureRecord {
  id?: string
  employee_number?: string | null
  name?: string | null
  department?: string | null
  position?: string | null
  offboarding_type?: string | null
  offboarding_date?: string | null
  reason?: string | null
  handover_status?: string | null
  created_at?: string | null
  updated_at?: string | null
  [key: string]: string | number | boolean | null | undefined
}

export interface OnboardingRecordListResponse {
  code: number
  message: string
  data: OnboardingRecord[]
  meta?: { page: number; page_size: number; total: number }
}

export interface DepartureRecordListResponse {
  code: number
  message: string
  data: DepartureRecord[]
  meta?: { page: number; page_size: number; total: number }
}

export interface TurnoverAnalysisResponse {
  code: number
  message: string
  data: {
    ai_summary: string
    ai_suggestions: Array<{ suggestion: string; evidence: string }>
    metrics: { turnover_rate: number }
    raw_data: {
      period_start: string
      period_end: string
      onboarding_count: number
      departure_count: number
      departure_by_reason: Record<string, number>
    }
  }
}

/** 一键导出：单个生成的文档（文件名 + 字节流） */
export interface ExportedDoc {
  name: string
  bytes: ArrayBuffer
}

/** 一键导出：各 Tab 注册的导出函数（返回生成的文档列表，null 表示该表无内容跳过） */
export type TrainingDocExporter = () => Promise<ExportedDoc[] | null>

/** 培训三个表单之间的共享数据（签到表 → 通知 / 评估表自动联动） */
export interface TrainingSessionData {
  training_date?: string
  training_time_start?: string
  training_time_end?: string
  topic?: string
  content?: string
  training_method?: string
  instructor?: string
  location?: string
  department?: string
  trainee_departments?: string[]
  employee_names?: string[]
  /** 姓名→部门 映射（人员配置自带部门，用于签到表"受训人员部门"列） */
  employee_dept_map?: Record<string, string>
  actual_count?: number
  training_level?: string
  plan_year?: number
  issuer_department?: string
  issue_date?: string
  /** 评估表选择的考核方式（笔试/口试/实操/写总结），驱动口试/实操表联动 */
  assessment_method?: string
  /** 勾选附件培训内容条目（《名称》（编号）），口试 AI 出题的结构化文件来源 */
  checked_content?: { name: string; code: string | null }[]
}

/** 培训人员配置-人员项（UI 展示类型） */
export interface TrainingPersonnelItem {
  name: string
  employee_number?: string
  department?: string | null
}

/** 培训人员配置（UI 展示类型） */
export interface TrainingPersonnelConfig {
  id: string
  level: string
  department?: string | null
  config_name: string
  personnel: TrainingPersonnelItem[]
  remarks?: string | null
  updated_at?: string
}

/** 新员工（最近进厂，UI 展示类型） */
export interface NewHire {
  employee_number: string | null
  name: string
  department?: string | null
  factory_entry_date?: string | null
}

export interface TrainingNotificationData {
  department: string
  training_date: string
  subject: string
  training_time_start?: string
  training_time_end?: string
  location?: string
  trainer?: string
  content?: string
  trainee_names: string[]
  remarks?: string
  issuer_department?: string
  issue_date?: string
}

export interface TrainingEvaluationData {
  subject: string
  training_date?: string
  training_time_start?: string
  training_time_end?: string
  duration_hours?: number
  training_method?: string
  is_exam?: boolean
  trainer_type?: string
  trainer?: string
  department_personnel?: string
  expected_count?: number
  actual_count?: number
  absent_count?: number
  textbook?: string
  makeup_training?: boolean
  assessment_method?: string
  pass_count?: number
  fail_count?: number
  absent_exam_count?: number
  absent_exam_handling?: string
  excellent_count?: number
  qualified_count?: number
  unqualified_count?: number
  evaluation_conclusion?: string
  organizer?: string
  organizer_date?: string
  remarks?: string
}

export interface OnboardingEvaluationData {
  employee_name: string
  employee_number?: string
  gender?: string
  department_position?: string
  hire_date?: string
  training_period?: string
  regularization_date?: string
  assessment_contents?: string[]
  comprehensive_comment?: string
  is_qualified?: boolean
  assigned_position?: string
  assessment_method?: string
  dept_manager_signature?: string
  signature_date?: string
  remarks?: string
  dept_manager_agree?: boolean
  hr_manager_agree?: boolean
  qa_manager_agree?: boolean
  dept_manager?: string
  hr_manager?: string
  qa_manager?: string
  approval_date?: string
}

export interface TrainingLedgerRecord {
  id: string
  employee_number: string
  training_date: string
  training_subject: string
  training_method?: string | null
  duration_hours?: number | null
  location?: string | null
  trainer?: string | null
  assessment_result?: string | null
  source_type: string
  source_id?: string | null
  remarks?: string | null
  session_id?: string | null
  // SMP-HR-002-14 年度培训统计表字段
  training_datetime?: string | null
  training_content?: string | null
  teaching_dept?: string | null
  instructor?: string | null
  level_category?: string | null
  involved_depts?: string | null
  trainees?: string | null
  training_type?: string | null
  ledger_assessment_method?: string | null
  plan_source?: string | null
  drug_category?: string | null
  score_summary?: string | null
  // 台账多部门管理字段
  ledger_department?: string | null
  owner_deleted?: boolean | null
  second_level_status?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export type TrainingLedgerCreateInput = components['schemas']['TrainingLedgerCreate']
export type TrainingLedgerUpdateInput = components['schemas']['TrainingLedgerUpdate']

// TODO: 生成 schema 未包含响应包装类型，待后端 OpenAPI 补充后替换
export interface TrainingLedgerListResponse {
  code: number
  message: string
  data: TrainingLedgerRecord[]
  meta?: {
    page: number
    page_size: number
    total: number
  }
}

// ─── ESG 培训报表 ───

export interface EsgTrainingRecord {
  id: string
  training_date: string
  training_name: string
  training_method?: string | null
  caliber?: string | null
  training_type?: string | null
  employee_name: string
  employee_account?: string | null
  location_address?: string | null
  department?: string | null
  employee_level?: string | null
  gender?: string | null
  age?: number | null
  duration?: number | null
  remarks?: string | null
  apply_company?: string | null
  apply_company_no?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface EsgTrainingRecordListResponse {
  code: number
  message: string
  data: EsgTrainingRecord[]
  meta?: {
    page: number
    page_size: number
    total: number
  }
}

// ─── AI 出题相关类型 ───

export interface ChoiceOption {
  label: string
  text: string
}

export interface ChoiceQuestion {
  number: number
  question: string
  options: ChoiceOption[]
  answer?: string
}

export interface TrueFalseQuestion {
  number: number
  question: string
  answer?: string
}

// TODO: 生成 schema 未包含响应包装类型，待后端 OpenAPI 补充后替换
export interface ExamGenerateResponse {
  code: number
  message: string
  data: {
    choice_questions: ChoiceQuestion[]
    true_false_questions: TrueFalseQuestion[]
  }
}

export interface ExamExportData {
  title: string
  examiner: string
  exam_date: string
  assessment_date: string
  choice_questions: ChoiceQuestion[]
  true_false_questions: TrueFalseQuestion[]
}

// ─── 口试 AI 出题类型（从 OpenAPI generated schema 导入，禁止手写） ───

export type OralExamFile = components['schemas']['OralExamFile']
export type OralExamGenerateRequest = components['schemas']['OralExamGenerateRequest']
export type OralExamQuestion = components['schemas']['OralExamQuestion']
export type OralExamGenerateResponse = components['schemas']['OralExamGenerateResponse']

/** 口试出题弹窗：单个文件的解析结果与补充文本（前端 UI 类型） */
export interface OralExamSourceFile {
  /** 文件名称（原始请求名） */
  name: string
  /** 匹配到的文件编码 */
  code?: string | null
  /** 是否在质量文件管理中匹配到条目 */
  matched: boolean
  /** 命中的附件数（有标准 MD 内容的） */
  attachmentCount: number
  /** 附件标准 MD 内容拼接（有效出题材料） */
  resolvedContent?: string
  /** 未匹配/无内容时用户手动粘贴的文本 */
  manualText?: string
}

// ─── AI 笔试（选择+填空）类型 ───

export interface FillBlankQuestion {
  number: number
  question: string
  answer?: string
}

export interface AiWrittenExamPayload {
  /** 试卷标题（可编辑，默认取培训内容 session.topic） */
  title?: string
  files: { name: string; code?: string; content: string }[]
  uploaded_content: string
  manual_content: string
  single_choice_count: number
  multiple_choice_count: number
  true_false_count: number
  fill_blank_count: number
  choice_questions: ChoiceQuestion[]
  true_false_questions: TrueFalseQuestion[]
  fill_blank_questions: FillBlankQuestion[]
  /** 旧版草稿兼容字段（仅恢复时读取） */
  choice_count?: number
  choice_type?: 'single' | 'multiple' | 'mixed'
}

export interface WrittenExamGenerateResponse {
  choice_questions: ChoiceQuestion[]
  true_false_questions: TrueFalseQuestion[]
  fill_blank_questions: FillBlankQuestion[]
  /** 实际生成题数少于请求数量 */
  shortfall?: boolean
}

// ─── AnnualTrainingPlan Types ───

export interface AnnualTrainingPlan {
  id: string
  year: number
  department: string
  plan_level: string
  version?: string
  remarks?: string
  status: string
  created_at?: string
  updated_at?: string
}

// 附件相关类型：统一从 OpenAPI 生成 schema 导入（禁止手写后端 API 类型）
export type PlanAttachment = components['schemas']['PlanAttachmentResponse']
export type PlanAttachmentSection = components['schemas']['PlanAttachmentSectionResponse']
export type AttachmentPreview = components['schemas']['AttachmentPreview']
export type AttachmentPreviewTable = components['schemas']['AttachmentPreviewTable']

export type AnnualTrainingPlanCreateInput = components['schemas']['AnnualTrainingPlanCreate']

export type AnnualTrainingPlanUpdateInput = components['schemas']['AnnualTrainingPlanUpdate']

// TODO: 生成 schema 未包含响应包装类型，待后端 OpenAPI 补充后替换
export interface AnnualTrainingPlanListResponse {
  code: number
  message: string
  data: AnnualTrainingPlan[]
  meta?: {
    page: number
    page_size: number
    total: number
  }
}

export interface AnnualTrainingPlanItem {
  id: string
  plan_id: string
  month?: string
  training_month?: string
  trainee_count?: number
  duration_hours?: number
  content_and_textbook?: string
  content_textbook?: string
  target_audience?: string
  position_and_count?: string
  training_method?: string
  training_hours?: number
  confirmer?: string
  confirm_date?: string
  remarks?: string
  tracking_status?: string
  sort_order: number
  created_at?: string
  updated_at?: string
}

export type AnnualTrainingPlanItemBatchUpdateInput = components['schemas']['AnnualTrainingPlanItemBatchUpdate']

// ─── 招聘候选人（待后端实现）───

export interface ResumeAttachment {
  file_token: string
  name: string
  type: string
  size: number
}

export interface Candidate {
  id: string
  name: string
  contact?: string
  email?: string
  job_id?: string
  job_position?: string
  education?: string
  work_years?: number
  skills?: string[] | string
  match_rate?: number
  resume_score?: number
  fit_level?: string
  interview_status?: string
  interview_time?: string
  interviewer?: string
  remark?: string
  source_channel?: string
  phone?: string
  resume_url?: string
  resume_attachment?: ResumeAttachment
  department?: string
  feishu_record_id?: string
  feishu_sync_status?: string
  feishu_sync_error?: string
  created_at?: string
  updated_at?: string
}

// ─── 岗位调动管理类型 ───

export interface ApprovalStep {
  node: string
  label: string
  status: 'pending' | 'approved' | 'rejected' | 'skipped'
  signer?: string | null
  date?: string | null
  opinion?: string | null
}

export interface ApprovalFlow {
  current_step: number
  applicant_name?: string | null
  applicant_date?: string | null
  is_supervisor_level: boolean
  steps: ApprovalStep[]
}

// 基于 generated schema 的 PositionTransferRecordCreate，补充响应额外字段
export type PositionTransferRecord = components['schemas']['PositionTransferRecordCreate'] & {
  id: string
  employee?: Employee
  approval_flow?: ApprovalFlow
  created_at?: string
  updated_at?: string
}

export type PositionTransferRecordCreateInput = components['schemas']['PositionTransferRecordCreate']
export type PositionTransferRecordUpdateInput = components['schemas']['PositionTransferRecordUpdate']

// TODO: 生成 schema 未包含响应包装类型，待后端 OpenAPI 补充后替换
export interface PositionTransferRecordListResponse {
  code: number
  message: string
  data: PositionTransferRecord[]
  meta?: {
    page: number
    page_size: number
    total: number
  }
}

// ─── HR 飞书设置相关类型 ───

export type HrFeishuFieldMappingItem = components['schemas']['HrFeishuFieldMappingItem']

export interface HrFeishuAppSettingsDetail {
  app_id: string
  app_secret_masked?: string | null
  is_enabled: boolean
  last_test_status?: string | null
  last_test_error?: string | null
  last_tested_at?: string | null
}

export type UpdateHrFeishuAppSettingsRequest = components['schemas']['UpdateHrFeishuAppSettingsRequest']

export interface HrFeishuEntitySettingItem {
  entity_code: string
  entity_name: string
  entity_group: string
  source_note?: string | null
  app_token?: string | null
  base_table_name?: string | null
  base_table_id?: string | null
  is_enabled: boolean
  enable_push_to_feishu: boolean
  enable_pull_from_feishu: boolean
  field_mappings?: HrFeishuFieldMappingItem[]
  sort_order: number
  last_sync_status?: string | null
  last_sync_error?: string | null
  last_synced_at?: string | null
}

export type UpdateHrFeishuEntitySettingRequest = components['schemas']['UpdateHrFeishuEntitySettingRequest']

export interface HrFeishuSettingsTestResult {
  success: boolean
  message: string
  checked_at: string
  entity_code?: string | null
  table_id?: string | null
}

export interface HrFeishuTableOption {
  table_id: string
  table_name: string
}

export interface HrFeishuFieldOption {
  field_id: string
  field_name: string
  field_type?: string | number | null
}

export interface HrFeishuSystemFieldOption {
  field_key: string
  field_label: string
  direction: string
}

export interface HrFeishuEntityFieldMappingBundle {
  entity_code: string
  entity_name: string
  system_fields: HrFeishuSystemFieldOption[]
  feishu_fields: HrFeishuFieldOption[]
  field_mappings: HrFeishuFieldMappingItem[]
}

// ═══════════════════════════════════════════════════════════════
// 培训管理二次开发新增类型（SMP-HR-002-14）
// ═══════════════════════════════════════════════════════════════

// ─── 培训师管理 ───

export interface Trainer {
  id: string
  name: string
  employee_id?: string | null
  department?: string | null
  position?: string | null
  approval_date?: string | null
  approver?: string | null
  remarks?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface TrainerCreateInput {
  name: string
  employee_id?: string | null
  department?: string | null
  position?: string | null
  approval_date?: string | null
  approver?: string | null
  remarks?: string | null
}

export interface TrainerUpdateInput {
  name?: string
  employee_id?: string | null
  department?: string | null
  position?: string | null
  approval_date?: string | null
  approver?: string | null
  remarks?: string | null
}

// ─── 培训评估表 ───

export interface TrainingEvaluation {
  id: string
  training_content?: string | null
  training_date?: string | null
  duration_hours?: number | null
  training_method?: string | null
  other_method?: string | null
  instructor?: string | null
  target_dept_person?: string | null
  expected_count?: number | null
  actual_count?: number | null
  absent_count?: number | null
  textbook?: string | null
  absent_handling?: string | null
  need_retraining?: boolean | null
  retraining_info?: string | null
  assessment_method?: string | null
  excellent_count?: number | null
  good_count?: number | null
  pass_count?: number | null
  fail_count?: number | null
  absent_exam_count?: number | null
  fail_handling?: string | null
  makeup_count?: number | null
  makeup_pass_count?: number | null
  makeup_fail_count?: number | null
  makeup_fail_handling?: string | null
  evaluation_result?: string | null
  evaluation_comment?: string | null
  evaluator?: string | null
  evaluate_date?: string | null
  has_notification?: boolean | null
  has_signin_sheet?: boolean | null
  has_textbook?: boolean | null
  has_exam_paper?: boolean | null
  has_score_summary?: boolean | null
  other_attachment?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export type TrainingEvaluationCreateInput = Omit<TrainingEvaluation, 'id' | 'created_at' | 'updated_at'>

export type TrainingEvaluationUpdateInput = Partial<TrainingEvaluationCreateInput>

// ─── 岗位培训清单 ───

export interface PositionTrainingListItem {
  id: string
  list_id: string
  level: string  // '部门级' | '岗位级'
  sort_order?: number | null
  textbook_name?: string | null
  textbook_code?: string | null
  assessment_method?: string | null
  remarks?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface PositionTrainingList {
  id: string
  department: string
  position: string
  creator?: string | null
  create_date?: string | null
  reviewer?: string | null
  review_date?: string | null
  approver?: string | null
  approve_date?: string | null
  items: PositionTrainingListItem[]
  created_at?: string | null
  updated_at?: string | null
}

export interface PositionTrainingListItemInput {
  level: string
  sort_order?: number | null
  textbook_name?: string | null
  textbook_code?: string | null
  assessment_method?: string | null
  remarks?: string | null
}

export interface PositionTrainingListCreateInput {
  department: string
  position: string
  creator?: string | null
  create_date?: string | null
  reviewer?: string | null
  review_date?: string | null
  approver?: string | null
  approve_date?: string | null
  items?: PositionTrainingListItemInput[]
}

export type PositionTrainingListUpdateInput = Partial<Omit<PositionTrainingListCreateInput, 'items'>>

// ─── 培训计划跟踪 ───

export interface PlanTrackingRecord {
  id: string
  plan_id?: string | null
  plan_item_id?: string | null
  year?: number | null
  month?: string | null
  plan_level?: string | null
  department?: string | null
  sort_order?: number | null
  training_content?: string | null
  actual_time?: string | null
  target_audience?: string | null
  training_type?: string | null
  tracking_assessment_method?: string | null
  is_completed?: boolean | null
  tracker?: string | null
  track_date?: string | null
  remarks?: string | null
  sessions_snapshot?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface PlanTrackingRecordCreateInput {
  plan_id?: string | null
  plan_item_id?: string | null
  year?: number | null
  month?: string | null
  plan_level?: string | null
  department?: string | null
  sort_order?: number | null
  training_content?: string | null
  actual_time?: string | null
  target_audience?: string | null
  training_type?: string | null
  tracking_assessment_method?: string | null
  is_completed?: boolean | null
  tracker?: string | null
  track_date?: string | null
  remarks?: string | null
  sessions_snapshot?: string | null
}

export type PlanTrackingRecordUpdateInput = Partial<PlanTrackingRecordCreateInput>


// ─── 新员工培训（NewEmployeeTrainingPlan）───

/** 新员工培训计划项（从岗位培训清单复制的教材快照） */
export interface NewEmployeeTrainingItem {
  id?: string | null
  level: string
  textbook_name: string
  textbook_code?: string | null
  assessment_method?: string | null
  remark?: string | null
  manual?: boolean
  sort_order?: number
  /** 完成日期（从培训台账实时计算，未完成则为空） */
  completed_date?: string | null
}

/** 新员工培训计划 - 详情（含实时进度） */
export interface NewEmployeeTrainingPlan {
  id: string
  employee_id: string
  employee_name: string
  employee_number?: string | null
  department: string
  sub_department?: string | null
  position: string
  hire_date: string
  deadline_date: string
  items: NewEmployeeTrainingItem[]
  status: string
  total_count: number
  completed_count: number
  progress: number
  created_at?: string | null
  updated_at?: string | null
}

/** 新员工培训列表项（已有计划或待生成计划的员工） */
export interface NewEmployeeTrainingListItem {
  plan_id?: string | null
  employee_id: string
  employee_name: string
  employee_number?: string | null
  department: string
  sub_department?: string | null
  position: string
  hire_date: string
  deadline_date?: string | null
  status?: string | null
  total_count: number
  completed_count: number
  progress: number
  training_position?: string | null
}

/** 新员工培训统计 */
export interface NewEmployeeTrainingStats {
  pending: number
  training: number
  completed: number
  overdue: number
}

/** 开始培训结果（跳转培训资料页面预填） */
export interface NewEmployeeTrainingStartResult {
  session_id: string
  topic: string
  employee_names: string[]
  employee_dept_map: Record<string, string>
  department: string
  training_level: string
  plan_year?: number | null
}

/** 生成/更新/添加计划项请求（API 类型来自 generated schema） */
export type NewEmployeeTrainingPlanGenerateInput = components['schemas']['NewEmployeeTrainingPlanGenerate']
export type NewEmployeeTrainingUpdateInput = components['schemas']['NewEmployeeTrainingPlanUpdate']
export type NewEmployeeTrainingItemAddInput = components['schemas']['NewEmployeeTrainingItemAdd']
export type NewEmployeeTrainingStartInput = components['schemas']['NewEmployeeTrainingStartRequest']
export type NewEmployeeTrainingManualAddInput = components['schemas']['NewEmployeeTrainingManualAdd']

// ─── 岗位培训映射（PositionTrainingMapping）───

export type PositionTrainingMappingCreateInput = components['schemas']['PositionTrainingMappingCreate']

/** 岗位培训映射 - ViewModel（后端经 success_response 包装，未生成独立 schema） */
export interface PositionTrainingMappingResponse {
  id: string
  department: string
  employee_position: string
  training_position: string
  created_at?: string | null
}

// ─── 合同审批结果（ContractApprovalResult）───

/** 合同审批结果 - ViewModel（后端 paginated_response 包装，未生成独立 schema） */
export interface ContractApprovalResultVM {
  id: string
  employee_number: string
  name: string
  dept_level1?: string | null
  dept_level2?: string | null
  contract_sequence?: string | null
  contract_end_date?: string | null
  approval_status?: string | null
  contract_opinion?: string | null
  dept_leader_name?: string | null
  supervisor_name?: string | null
  dept_approved_at?: string | null
  supervisor_approved_at?: string | null
  completed_at?: string | null
  signed_status?: string | null
  signed_at?: string | null
  created_at?: string | null
}

/** 合同审批结果筛选条件 */
export interface ContractApprovalResultQuery {
  start_date?: string
  end_date?: string
  department?: string
  result?: 'approved' | 'rejected'
  page?: number
  page_size?: number
}
