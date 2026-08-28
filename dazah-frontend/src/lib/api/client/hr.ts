/**
 * HR 模块 - 客户端 API（浏览器 GET/list/search/detail）
 * 使用相对路径 /api/v1/...
 */

import type { components } from '@/types/generated/schema'
import type {
  Trainer,
  TrainingEvaluation,
  PositionTrainingList,
  PlanTrackingRecord,
  AnnualTrainingPlan,
  AnnualTrainingPlanItem,
  AnnualTrainingPlanListResponse,
  PlanAttachment,
  PlanAttachmentSection,
  AttachmentPreview,
  NewEmployeeTrainingListItem,
  NewEmployeeTrainingPlan,
  NewEmployeeTrainingStats,
  PositionTrainingMappingResponse,
  ContractApprovalResultQuery,
  ContractApprovalResultVM,
  Candidate,
  Department,
} from '@/types/hr'

export interface JobPostingVM {
  id: string
  title: string
  description?: string | null
  requirement?: string | null
  salary_range?: string | null
  location?: string | null
  req_skills?: string[] | null
  candidate_count?: number
}

export interface OnboardingListItem {
  id: string
  name: string
  onboard_date?: string
  department?: string
  level?: string
  status?: string
  health_status?: string
  resignation_cert?: string
  id_card?: string
  education_cert?: string
  created_at?: string
  updated_at?: string
}

// ─── 员工 ───

export async function fetchMaxSeqNumber(): Promise<{ code: number; data: { max_seq: number; next_seq: number } }> {
  const res = await fetch('/api/v1/hr/employees/max-seq', { cache: 'no-store' })
  if (!res.ok) throw new Error('获取最大序号失败')
  return res.json()
}

// ─── 招聘职位 ────

export async function fetchDepartments(
  params?: { keyword?: string; page?: number; page_size?: number }
): Promise<{ code: number; message: string; data: Department[]; meta?: { total: number } }> {
  const searchParams = new URLSearchParams()
  if (params?.keyword) searchParams.set('keyword', params.keyword)
  searchParams.set('page', String(params?.page || 1))
  searchParams.set('page_size', String(params?.page_size || 200))
  const res = await fetch(`/api/v1/hr/departments?${searchParams.toString()}`, { cache: 'no-store' })
  if (!res.ok) throw new Error('获取部门列表失败')
  return res.json()
}

export async function fetchJobPostings(
  params?: { keyword?: string; page?: number; page_size?: number }
): Promise<{ code: number; message: string; data: JobPostingVM[]; meta?: { total: number; page: number; page_size: number } }> {
  const searchParams = new URLSearchParams()
  if (params?.keyword) searchParams.set('keyword', params.keyword)
  searchParams.set('page', String(params?.page || 1))
  searchParams.set('page_size', String(params?.page_size || 100))
  const res = await fetch(`/api/v1/hr/jobs?${searchParams.toString()}`, { cache: 'no-store' })
  if (!res.ok) throw new Error('获取职位列表失败')
  return res.json()
}

export async function fetchJobPostingById(id: string): Promise<{ code: number; message: string; data: JobPostingVM }> {
  const res = await fetch(`/api/v1/hr/jobs/${id}`, { cache: 'no-store' })
  if (!res.ok) throw new Error('获取职位详情失败')
  return res.json()
}

// ─── 招聘候选人 ───

export async function fetchCandidates(
  params?: { keyword?: string; fit_level?: string; interview_status?: string; job_id?: string; page?: number; page_size?: number }
): Promise<{ code: number; message: string; data: Candidate[]; meta?: { total: number; page: number; page_size: number } }> {
  const searchParams = new URLSearchParams()
  if (params?.keyword) searchParams.set('keyword', params.keyword)
  if (params?.fit_level) searchParams.set('fit_level', params.fit_level)
  if (params?.interview_status) searchParams.set('interview_status', params.interview_status)
  if (params?.job_id) searchParams.set('job_id', params.job_id)
  searchParams.set('page', String(params?.page || 1))
  searchParams.set('page_size', String(params?.page_size || 20))
  const res = await fetch(`/api/v1/hr/candidates?${searchParams.toString()}`, { cache: 'no-store' })
  if (!res.ok) throw new Error('获取候选人列表失败')
  return res.json()
}

export async function fetchCandidateById(id: string): Promise<{ code: number; message: string; data: Candidate }> {
  const res = await fetch(`/api/v1/hr/candidates/${id}`, { cache: 'no-store' })
  if (!res.ok) throw new Error('获取候选人详情失败')
  return res.json()
}

// ─── 入职管理 ───

export async function fetchOnboardingList(
  params?: { keyword?: string; page?: number; page_size?: number }
): Promise<{ code: number; message: string; data: OnboardingListItem[]; meta?: { total: number; page: number; page_size: number } }> {
  const searchParams = new URLSearchParams()
  if (params?.keyword) searchParams.set('keyword', params.keyword)
  searchParams.set('page', String(params?.page || 1))
  searchParams.set('page_size', String(params?.page_size || 20))
  const res = await fetch(`/api/v1/hr/onboarding?${searchParams.toString()}`, { cache: 'no-store' })
  if (!res.ok) throw new Error('获取入职列表失败')
  return res.json()
}

export async function fetchOnboardingById(id: string): Promise<{ code: number; message: string; data: OnboardingListItem }> {
  const res = await fetch(`/api/v1/hr/onboarding/${id}`, { cache: 'no-store' })
  if (!res.ok) throw new Error('获取入职详情失败')
  return res.json()
}

export async function fetchOnboardingDashboard(): Promise<{ code: number; message: string; data: { stages: Record<string, { count: number; label: string }>; total: number } }> {
  const res = await fetch('/api/v1/hr/onboarding/dashboard', { cache: 'no-store' })
  if (!res.ok) throw new Error('获取入职看板失败')
  return res.json()
}

export async function fetchOnboardingNames(): Promise<string[]> {
  const res = await fetch('/api/v1/hr/onboarding/names', { cache: 'no-store' })
  if (!res.ok) throw new Error('获取姓名列表失败')
  const data = await res.json()
  return data.data || []
}

// ─── HR设置中心：提醒配置 ───
// 注意：后端 success_response 泛型包装导致 OpenAPI 未生成 Response 类型，
// 此处使用 ViewModel 类型（规范允许手写前端 ViewModel/display 类型）

export interface ReminderConfigVM {
  id: string
  entity_code: string
  entity_label: string
  module_group: string
  reminder_type: string
  reminder_label: string
  reminder_days: number[]
  recipient_open_ids: string[]
  recipient_names: string[]
  dept_notify_enabled: boolean
  trigger_frequency: string
  trigger_day: number
  trigger_hour: number
  notify_hours: number
  message_template: string
  sign_clerk_open_ids: string[]
  sign_clerk_names: string[]
  sign_reminder_days: number
  is_enabled: boolean
  sort_order: number
}

export interface ApprovalConfigVM {
  id: string
  entity_code: string
  entity_label: string
  module_group: string
  role: string
  role_label: string
  approver_open_ids: string[]
  approver_names: string[]
  deadline_days: number | null
  sort_order: number
}

export interface DeptRecipientVM {
  id?: string
  reminder_config_id: string
  department: string
  recipient_open_ids: string[]
  recipient_names: string[]
  use_dept_leader: boolean
}

export async function fetchReminderConfigs(): Promise<ReminderConfigVM[]> {
  const res = await fetch('/api/v1/hr/hr-settings/reminders', { cache: 'no-store' })
  if (!res.ok) throw new Error('获取提醒配置失败')
  const json = await res.json()
  return (json.data ?? []) as ReminderConfigVM[]
}

export async function fetchApprovalConfigs() {
  const res = await fetch('/api/v1/hr/hr-settings/approvals', { cache: 'no-store' })
  const json = await res.json()
  return json.data as ApprovalConfigVM[]
}

// ─── 部门级提醒接收人 ───

export async function fetchDeptRecipients(configId: string) {
  const res = await fetch(`/api/v1/hr/hr-settings/reminders/${configId}/dept-recipients`, { cache: 'no-store' })
  const json = await res.json()
  return json.data as DeptRecipientVM[]
}

// ─── HR 通知人员 ───

export interface HrMemberVM {
  name: string
  open_id: string
  department: string
}

export async function fetchHrMembers(): Promise<HrMemberVM[]> {
  const res = await fetch('/api/v1/hr/hr-settings/hr-members', { cache: 'no-store' })
  if (!res.ok) throw new Error('获取人员列表失败')
  const json = await res.json()
  return (json.data ?? []) as HrMemberVM[]
}

// ─── 飞书联系人列表（分页+搜索）───

export interface FeishuContactVM {
  id: string
  open_id: string
  name: string
  department: string | null
  mobile: string | null
  email: string | null
  enterprise_email: string | null
  employee_no: string | null
  job_title: string | null
  gender: string | null
  avatar_url: string | null
  status: string | null
  status_changed_at: string | null
}

export async function fetchFeishuMembers(params?: {
  page?: number
  page_size?: number
  keyword?: string
  department?: string
  status?: string
}) {
  const p = new URLSearchParams()
  p.set('page', String(params?.page || 1))
  p.set('page_size', String(params?.page_size || 20))
  if (params?.keyword) p.set('keyword', params.keyword)
  if (params?.department) p.set('department', params.department)
  if (params?.status) p.set('status', params.status)

  const res = await fetch(`/api/v1/hr/hr-settings/feishu-members?${p.toString()}`, { cache: 'no-store' })
  if (!res.ok) throw new Error('获取飞书联系人失败')
  return res.json() as Promise<{
    code: number
    message: string
    data: FeishuContactVM[]
    meta: { page: number; page_size: number; total: number }
  }>
}

// ─── 飞书联系人筛选部门选项 ───

export async function fetchFeishuMemberDepartments(): Promise<{
  code: number
  message: string
  data: string[]
}> {
  const res = await fetch('/api/v1/hr/hr-settings/feishu-members/departments', { cache: 'no-store' })
  if (!res.ok) throw new Error('获取飞书联系人部门选项失败')
  return res.json()
}

// ─── 年度培训计划 ───

export async function fetchAnnualTrainingPlans(
  params?: {
    year?: number
    department?: string
    page?: number
    page_size?: number
  }
): Promise<AnnualTrainingPlanListResponse> {
  const searchParams = new URLSearchParams()
  if (params?.year) searchParams.set('year', String(params.year))
  if (params?.department) searchParams.set('department', params.department)
  searchParams.set('page', String(params?.page || 1))
  searchParams.set('page_size', String(params?.page_size || 100))

  const res = await fetch(`/api/v1/hr/annual-training-plans?${searchParams.toString()}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取年度培训计划列表失败')
  return res.json()
}

export async function fetchAnnualTrainingPlanById(
  id: string
): Promise<{ code: number; message: string; data: AnnualTrainingPlan }> {
  const res = await fetch(`/api/v1/hr/annual-training-plans/${id}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取年度培训计划详情失败')
  return res.json()
}

export async function fetchPlanItems(
  id: string
): Promise<{ code: number; message: string; data: AnnualTrainingPlanItem[] }> {
  const res = await fetch(`/api/v1/hr/annual-training-plans/${id}/items`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取年度计划明细失败')
  return res.json()
}

export async function fetchPlanAttachments(
  planId: string
): Promise<{ code: number; message: string; data: PlanAttachment[] }> {
  const res = await fetch(`/api/v1/hr/annual-training-plans/${planId}/attachments`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取计划附件列表失败')
  return res.json()
}

export async function fetchPlanAttachmentSections(
  planId: string
): Promise<{ code: number; message: string; data: PlanAttachmentSection[] }> {
  const res = await fetch(`/api/v1/hr/annual-training-plans/${planId}/attachment-sections`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取计划附件条目失败')
  return res.json()
}

export async function fetchSectionPreview(
  sectionId: string
): Promise<{ code: number; message: string; data: AttachmentPreview | null }> {
  const res = await fetch(`/api/v1/hr/plan-attachment-sections/${sectionId}/preview`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取附件条目预览失败')
  return res.json()
}

export async function fetchAttachmentPreview(
  attachmentId: string
): Promise<{ code: number; message: string; data: AttachmentPreview | null }> {
  const res = await fetch(`/api/v1/hr/annual-training-plan-attachments/${attachmentId}/preview`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取附件预览失败')
  return res.json()
}

/** 已培训/已导入台账的附件文件清单条目（用于置灰不可再选） */
export async function fetchUsedTrainingContent(): Promise<
  { entry_name: string; entry_code: string | null; used_at: string | null }[]
> {
  const res = await fetch('/api/v1/hr/training-content-used', { cache: 'no-store' })
  if (!res.ok) throw new Error('获取已培训文件清单失败')
  const json = await res.json()
  return json.data ?? []
}

// ─── 培训会话/资料（保存历史+台账关联回看） ───
// 说明：后端响应走统一 envelope，Out 类型未进 OpenAPI，此处为展示层 ViewModel 类型

export interface TrainingSessionVM {
  id: string
  training_level?: string | null
  plan_year?: number | null
  department?: string | null
  trainee_departments?: string[] | null
  topic?: string | null
  training_date?: string | null
  time_start?: string | null
  time_end?: string | null
  training_method?: string | null
  instructor?: string | null
  actual_count?: number | null
  employee_names?: string[] | null
  employee_dept_map?: Record<string, string> | null
  checked_content?: { name: string; code: string | null }[] | null
}

export interface TrainingDocumentVM {
  id: string
  session_id: string
  doc_type: string
  title?: string | null
  payload: Record<string, unknown>
  updated_at?: string | null
}

export async function fetchTrainingSession(sessionId: string): Promise<TrainingSessionVM> {
  const res = await fetch(`/api/v1/hr/training-sessions/${sessionId}`, { cache: 'no-store' })
  if (!res.ok) throw new Error('获取培训会话失败')
  const json = await res.json()
  return json.data
}

export async function fetchSessionDocuments(sessionId: string): Promise<TrainingDocumentVM[]> {
  const res = await fetch(`/api/v1/hr/training-sessions/${sessionId}/documents`, { cache: 'no-store' })
  if (!res.ok) throw new Error('获取会话资料列表失败')
  const json = await res.json()
  return json.data ?? []
}

export async function fetchTrainingDocument(docId: string): Promise<TrainingDocumentVM> {
  const res = await fetch(`/api/v1/hr/training-documents/${docId}`, { cache: 'no-store' })
  if (!res.ok) throw new Error('获取培训资料失败')
  const json = await res.json()
  return json.data
}

/** 导出年度培训计划 Word 文档（公司级 APP2 模板 / 部门级 APP1 模板） */
export async function exportAnnualTrainingPlanWord(
  planId: string,
  isCompanyLevel = false
): Promise<void> {
  const res = await fetch(`/api/v1/hr/annual-training-plans/${planId}/export`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('导出年度培训计划Word失败')
  const blob = await res.blob()

  // 优先解析后端返回的文件名（filename*=utf-8'' 编码）
  let filename = `年度培训计划_${isCompanyLevel ? '公司级' : '部门级'}.docx`
  const disposition = res.headers.get('content-disposition') || ''
  const match = disposition.match(/filename\*=utf-8''([^;]+)/i)
  if (match) filename = decodeURIComponent(match[1])

  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

// ─── 飞书联系人搜索（轻量级，用于选择器）───

export async function searchFeishuMembers(keyword: string) {
  if (!keyword || keyword.length < 1) return []
  const p = new URLSearchParams()
  p.set('page', '1')
  p.set('page_size', '10')
  p.set('keyword', keyword)
  p.set('status', '1') // 只查在职

  const res = await fetch(`/api/v1/hr/hr-settings/feishu-members?${p.toString()}`, {
    cache: 'no-store',
    credentials: 'include',
  })
  if (!res.ok) {
    console.error('searchFeishuMembers failed:', res.status, await res.text().catch(() => ''))
    return []
  }
  const json = await res.json()
  return (json.data || []) as FeishuContactVM[]
}

// ─── 培训人员配置 / 新员工 ───

export async function fetchTrainingPersonnelConfigs(
  params?: { level?: string; department?: string }
): Promise<{ code: number; message: string; data: import('@/types/hr').TrainingPersonnelConfig[] }> {
  const sp = new URLSearchParams()
  if (params?.level) sp.set('level', params.level)
  if (params?.department) sp.set('department', params.department)
  const res = await fetch(`/api/v1/hr/training-personnel-configs?${sp.toString()}`, { cache: 'no-store' })
  if (!res.ok) throw new Error('获取培训人员配置失败')
  return res.json()
}

export async function fetchNewHires(
  days = 7
): Promise<{ code: number; message: string; data: import('@/types/hr').NewHire[] }> {
  const res = await fetch(`/api/v1/hr/employees/new-hires?days=${days}`, { cache: 'no-store' })
  if (!res.ok) throw new Error('获取新员工失败')
  return res.json()
}

// ─── 部门级审批人配置 ───

export interface DeptApprovalConfigVM {
  id: string | null
  department_id: string
  department_name: string
  direct_leader_name: string | null
  direct_leader_open_id: string | null
  manager_name: string | null
  manager_open_id: string | null
  director_name: string | null
  director_open_id: string | null
  vp_name: string | null
  vp_open_id: string | null
  sort_order: number
}

export async function fetchDeptApprovalConfigs() {
  const res = await fetch('/api/v1/hr/dept-approval-configs', { cache: 'no-store' })
  if (!res.ok) throw new Error('获取部门审批配置失败')
  const json = await res.json()
  return json.data as DeptApprovalConfigVM[]
}

// ─── 岗位调动 ───

export async function fetchPositionTransfers(params?: {
  keyword?: string
  approval_status?: string
  page?: number
  page_size?: number
}) {
  const sp = new URLSearchParams()
  if (params?.keyword) sp.set('keyword', params.keyword)
  if (params?.approval_status) sp.set('approval_status', params.approval_status)
  sp.set('page', String(params?.page || 1))
  sp.set('page_size', String(params?.page_size || 20))
  const res = await fetch(`/api/v1/hr/position-transfers?${sp.toString()}`, { cache: 'no-store' })
  if (!res.ok) throw new Error('获取岗位调动列表失败')
  return res.json()
}

// ─── 合同管理 ───

export interface ContractVM {
  id: string
  employee_number: string
  name: string
  gender: string | null
  dept_level1: string | null
  dept_level2: string | null
  position: string | null
  job_level: string | null
  domain_account: string | null
  id_card: string | null
  id_card_expiry: string | null
  archive_number: string | null
  contract_sequence: string | null
  contract_start_1: string | null
  contract_end_1: string | null
  contract_start_2: string | null
  contract_end_2: string | null
  contract_start_3: string | null
  contract_end_3: string | null
  contract_start_4: string | null
  contract_end_4: string | null
  contract_start_5: string | null
  contract_end_5: string | null
  contract_start_6: string | null
  contract_end_6: string | null
  dept_leader_name: string | null
  contract_opinion: string | null
  approval_status: string | null
  supervisor_name: string | null
  supervisor_open_id: string | null
  dept_approved_at: string | null
  supervisor_approved_at: string | null
  signed_status: string | null
  signed_at: string | null
  sign_reminded_at: string | null
  created_at: string
  updated_at: string
}

export async function fetchContracts(params?: Record<string, unknown>): Promise<{ data: ContractVM[]; total: number }> {
  const sp = new URLSearchParams()
  if (params) Object.entries(params).forEach(([k, v]) => { if (v != null) sp.set(k, String(v)) })
  const res = await fetch(`/api/v1/hr/contracts?${sp}`, { cache: 'no-store' })
  if (!res.ok) throw new Error('获取合同列表失败')
  return res.json()
}

// ═══════════════════════════════════════════════════════════════
// 培训管理二次开发新增 API（SMP-HR-002-14）
// ═══════════════════════════════════════════════════════════════

// ─── 培训师管理 ───

export async function fetchTrainers(
  params?: { keyword?: string; department?: string; page?: number; page_size?: number }
): Promise<{ data: Trainer[]; total: number; page: number; page_size: number }> {
  const sp = new URLSearchParams()
  if (params?.keyword) sp.set('keyword', params.keyword)
  if (params?.department) sp.set('department', params.department)
  sp.set('page', String(params?.page || 1))
  sp.set('page_size', String(params?.page_size || 20))
  const res = await fetch(`/api/v1/hr/trainers?${sp}`, { cache: 'no-store' })
  if (!res.ok) throw new Error('获取培训师列表失败')
  const json = await res.json()
  return {
    data: json.data || [],
    total: json.meta?.total || 0,
    page: json.meta?.page || 1,
    page_size: json.meta?.page_size || 20,
  }
}

/** 培训模块所有有数据的部门（台账/ESG/年度计划/岗位清单/培训师/培训会话 并集） */
export async function fetchTrainingDepartments(): Promise<string[]> {
  const res = await fetch('/api/v1/hr/training/departments', { cache: 'no-store' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || err.detail || '获取培训部门列表失败')
  }
  const json = await res.json()
  return json.data || []
}

/** 获取手动添加的自定义培训部门列表（用于判断哪些部门可删除） */
export async function fetchCustomTrainingDepartments(): Promise<string[]> {
  const res = await fetch('/api/v1/hr/training/departments/custom', { cache: 'no-store' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || err.detail || '获取自定义部门列表失败')
  }
  const json = await res.json()
  return json.data || []
}

// ─── 培训部门映射配置（HR 设置维护，前后端共用同一份数据源） ───

export interface DeptMappingItem {
  id: string
  source_name: string
  target_name: string | null
  match_level: 'first' | 'second' | 'both'
  mapping_type:
    | 'special'
    | 'alias'
    | 'candidate_source'
    | 'split'
    | 'print_unify'
    | 'modal_drop'
    | 'modal_extra'
    | 'modal_no_expand'
    | 'exclude'
    | 'force_show'
  priority: number
  enabled: boolean
  remark: string | null
  created_at: string | null
  updated_at: string | null
}

/** 培训部门映射配置列表（解析规则统一数据源，替代前端硬编码字典） */
export async function fetchTrainingDeptMappings(): Promise<DeptMappingItem[]> {
  const res = await fetch('/api/v1/hr/training/dept-mappings', { cache: 'no-store' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || err.detail || '获取培训部门映射配置失败')
  }
  const json = await res.json()
  return json.data || []
}

export type DeptMappingPayload = Omit<DeptMappingItem, 'id' | 'created_at' | 'updated_at'>

export async function createTrainingDeptMapping(
  data: Partial<DeptMappingPayload>,
): Promise<DeptMappingItem> {
  const res = await fetch('/api/v1/hr/training/dept-mappings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || err.detail || '新增映射失败')
  }
  return (await res.json()).data
}

export async function updateTrainingDeptMapping(
  id: string,
  data: Partial<DeptMappingPayload>,
): Promise<DeptMappingItem> {
  const res = await fetch(`/api/v1/hr/training/dept-mappings/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || err.detail || '更新映射失败')
  }
  return (await res.json()).data
}

export async function deleteTrainingDeptMapping(id: string): Promise<void> {
  const res = await fetch(`/api/v1/hr/training/dept-mappings/${id}`, { method: 'DELETE' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || err.detail || '删除映射失败')
  }
}

// ─── 用户可见部门配置（部门级数据隔离，管理员） ───

export interface DeptScopeItem {
  user_id: string
  user_name: string
  user_department: string
  visible_depts: string[]
  updated_at: string | null
}

export async function fetchDeptScopes(): Promise<DeptScopeItem[]> {
  const res = await fetch('/api/v1/hr/dept-scopes', { cache: 'no-store' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || err.detail || '获取可见部门配置失败')
  }
  const json = await res.json()
  return json.data || []
}

export async function fetchDeptScope(userId: string): Promise<{ user_id: string; visible_depts: string[] }> {
  const res = await fetch(`/api/v1/hr/dept-scopes/${userId}`, { cache: 'no-store' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || err.detail || '获取用户可见部门配置失败')
  }
  const json = await res.json()
  return json.data || { user_id: userId, visible_depts: [] }
}

export async function saveDeptScope(
  userId: string,
  visibleDepts: string[],
  userMeta?: { user_name?: string; user_department?: string }
): Promise<{ user_id: string; visible_depts: string[] }> {
  const res = await fetch(`/api/v1/hr/dept-scopes/${userId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      visible_depts: visibleDepts,
      user_name: userMeta?.user_name,
      user_department: userMeta?.user_department,
    }),
    cache: 'no-store',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || err.detail || '保存可见部门配置失败')
  }
  const json = await res.json()
  return json.data
}

export async function clearDeptScope(userId: string): Promise<void> {
  const res = await fetch(`/api/v1/hr/dept-scopes/${userId}`, {
    method: 'DELETE',
    cache: 'no-store',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || err.detail || '清除可见部门配置失败')
  }
}

// ─── 员工培训清单 ───

export type EmployeeTrainingMemberItem = components['schemas']['EmployeeTrainingListMemberOut']
export type EmployeeTrainingRecordItem = components['schemas']['EmployeeTrainingRecordOut']

export async function fetchEmployeeTrainingMembers(
  department: string
): Promise<EmployeeTrainingMemberItem[]> {
  const res = await fetch(
    `/api/v1/hr/training/employee-training-list/members?department=${encodeURIComponent(department)}`,
    { cache: 'no-store' }
  )
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || err.detail || '获取部门配置人员失败')
  }
  const json = await res.json()
  return json.data || []
}

export async function fetchEmployeeTrainingRecords(
  name: string,
  date_from?: string,
  date_to?: string
): Promise<EmployeeTrainingRecordItem[]> {
  const sp = new URLSearchParams({ name })
  if (date_from) sp.set('date_from', date_from)
  if (date_to) sp.set('date_to', date_to)
  const res = await fetch(`/api/v1/hr/training/employee-training-list/records?${sp.toString()}`, {
    cache: 'no-store',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || err.detail || '获取个人培训记录失败')
  }
  const json = await res.json()
  return json.data || []
}

export async function fetchTrainerById(id: string): Promise<Trainer> {
  const res = await fetch(`/api/v1/hr/trainers/${id}`, { cache: 'no-store' })
  if (!res.ok) throw new Error('获取培训师详情失败')
  const json = await res.json()
  return json.data
}

// ─── 培训评估表 ───

export async function fetchTrainingEvaluations(
  params?: { keyword?: string; page?: number; page_size?: number }
): Promise<{ data: TrainingEvaluation[]; total: number; page: number; page_size: number }> {
  const sp = new URLSearchParams()
  if (params?.keyword) sp.set('keyword', params.keyword)
  sp.set('page', String(params?.page || 1))
  sp.set('page_size', String(params?.page_size || 20))
  const res = await fetch(`/api/v1/hr/training-evaluations?${sp}`, { cache: 'no-store' })
  if (!res.ok) throw new Error('获取培训评估表列表失败')
  const json = await res.json()
  return {
    data: json.data || [],
    total: json.meta?.total || 0,
    page: json.meta?.page || 1,
    page_size: json.meta?.page_size || 20,
  }
}

export async function fetchTrainingEvaluationById(id: string): Promise<TrainingEvaluation> {
  const res = await fetch(`/api/v1/hr/training-evaluations/${id}`, { cache: 'no-store' })
  if (!res.ok) throw new Error('获取培训评估表详情失败')
  const json = await res.json()
  return json.data
}

// ─── 岗位培训清单 ───

export async function fetchPositionTrainingLists(
  params?: { department?: string; page?: number; page_size?: number }
): Promise<{ data: PositionTrainingList[]; total: number; page: number; page_size: number }> {
  const sp = new URLSearchParams()
  if (params?.department) sp.set('department', params.department)
  sp.set('page', String(params?.page || 1))
  sp.set('page_size', String(params?.page_size || 20))
  const res = await fetch(`/api/v1/hr/position-training-lists?${sp}`, { cache: 'no-store' })
  if (!res.ok) throw new Error('获取岗位培训清单列表失败')
  const json = await res.json()
  return {
    data: json.data || [],
    total: json.meta?.total || 0,
    page: json.meta?.page || 1,
    page_size: json.meta?.page_size || 20,
  }
}

export async function fetchPositionTrainingListById(id: string): Promise<PositionTrainingList> {
  const res = await fetch(`/api/v1/hr/position-training-lists/${id}`, { cache: 'no-store' })
  if (!res.ok) throw new Error('获取岗位培训清单详情失败')
  const json = await res.json()
  return json.data
}


// ─── 培训计划跟踪 ───

export async function fetchPlanTrackingRecords(
  params?: { plan_id?: string; page?: number; page_size?: number }
): Promise<{ data: PlanTrackingRecord[]; total: number; page: number; page_size: number }> {
  const sp = new URLSearchParams()
  if (params?.plan_id) sp.set('plan_id', params.plan_id)
  sp.set('page', String(params?.page || 1))
  sp.set('page_size', String(params?.page_size || 20))
  const res = await fetch(`/api/v1/hr/plan-tracking?${sp}`, { cache: 'no-store' })
  if (!res.ok) throw new Error('获取培训计划跟踪列表失败')
  const json = await res.json()
  return {
    data: json.data || [],
    total: json.meta?.total || 0,
    page: json.meta?.page || 1,
    page_size: json.meta?.page_size || 20,
  }
}

export async function fetchPlanTrackingRecordById(id: string): Promise<PlanTrackingRecord> {
  const res = await fetch(`/api/v1/hr/plan-tracking/${id}`, { cache: 'no-store' })
  if (!res.ok) throw new Error('获取培训计划跟踪详情失败')
  const json = await res.json()
  return json.data
}

export async function fetchPlanTrackingPeriod(params: {
  year: number
  month: number
  plan_level: string
  department?: string | null
}): Promise<PlanTrackingRecord[]> {
  const sp = new URLSearchParams()
  sp.set('year', String(params.year))
  sp.set('month', String(params.month))
  sp.set('plan_level', params.plan_level)
  if (params.department) sp.set('department', params.department)
  const res = await fetch(`/api/v1/hr/plan-tracking/period?${sp}`, { cache: 'no-store' })
  if (!res.ok) throw new Error('获取培训计划跟踪期间数据失败')
  const json = await res.json()
  return json.data || []
}

// ─── 新员工培训 ───

export async function fetchNewEmployeeTrainingPlans(
  params?: {
    page?: number
    page_size?: number
    department?: string
    status?: string
    keyword?: string
    include_pending?: boolean
  }
): Promise<{ data: NewEmployeeTrainingListItem[]; total: number; page: number; page_size: number }> {
  const sp = new URLSearchParams()
  if (params?.department) sp.set('department', params.department)
  if (params?.status) sp.set('status', params.status)
  if (params?.keyword) sp.set('keyword', params.keyword)
  if (params?.include_pending === false) sp.set('include_pending', 'false')
  sp.set('page', String(params?.page || 1))
  sp.set('page_size', String(params?.page_size || 20))
  const res = await fetch(`/api/v1/hr/new-employee-training/plans?${sp}`, { cache: 'no-store' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || err.detail || '获取新员工培训列表失败')
  }
  const json = await res.json()
  return {
    data: json.data || [],
    total: json.meta?.total || 0,
    page: json.meta?.page || 1,
    page_size: json.meta?.page_size || 20,
  }
}

export async function fetchNewEmployeeTrainingPlan(id: string): Promise<NewEmployeeTrainingPlan> {
  const res = await fetch(`/api/v1/hr/new-employee-training/plans/${id}`, { cache: 'no-store' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || err.detail || '获取新员工培训计划详情失败')
  }
  const json = await res.json()
  return json.data
}

export async function fetchNewEmployeeTrainingStats(): Promise<NewEmployeeTrainingStats> {
  const res = await fetch('/api/v1/hr/new-employee-training/stats', { cache: 'no-store' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || err.detail || '获取新员工培训统计失败')
  }
  const json = await res.json()
  return json.data
}

export async function fetchAvailableTrainees(
  params?: { department?: string; exclude_plan_id?: string; page?: number; page_size?: number }
): Promise<{ name: string; department: string }[]> {
  const sp = new URLSearchParams()
  if (params?.department) sp.set('department', params.department)
  if (params?.exclude_plan_id) sp.set('exclude_plan_id', params.exclude_plan_id)
  sp.set('page', String(params?.page || 1))
  sp.set('page_size', String(params?.page_size || 50))
  const res = await fetch(`/api/v1/hr/new-employee-training/available-trainees?${sp}`, { cache: 'no-store' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || err.detail || '获取可培训人员列表失败')
  }
  const json = await res.json()
  return json.data || []
}

export async function exportPositionTrainingConfirmation(planId: string): Promise<Blob> {
  const res = await fetch(`/api/v1/hr/new-employee-training/plans/${planId}/export-confirmation`, {
    cache: 'no-store',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || err.detail || '导出岗位培训确认表失败')
  }
  return res.blob()
}

// ─── 岗位培训映射 ───

export async function fetchPositionTrainingMappings(
  department: string
): Promise<PositionTrainingMappingResponse[]> {
  const res = await fetch(
    `/api/v1/hr/position-training-mappings?department=${encodeURIComponent(department)}`,
    { cache: 'no-store' }
  )
  if (!res.ok) throw new Error('获取岗位映射列表失败')
  const json = await res.json()
  return json.data || []
}

export async function fetchDepartmentPositions(department: string): Promise<string[]> {
  const res = await fetch(
    `/api/v1/hr/position-training-lists/departments/${encodeURIComponent(department)}/positions`,
    { cache: 'no-store' }
  )
  if (!res.ok) throw new Error('获取部门岗位列表失败')
  const json = await res.json()
  return json.data || []
}

// ─── 合同审批结果 ───

export async function fetchContractApprovalResults(
  params: ContractApprovalResultQuery = {}
): Promise<{ code: number; data: ContractApprovalResultVM[]; meta?: { total?: number; page?: number; page_size?: number } }> {
  const searchParams = new URLSearchParams()
  if (params.start_date) searchParams.set('start_date', params.start_date)
  if (params.end_date) searchParams.set('end_date', params.end_date)
  if (params.department) searchParams.set('department', params.department)
  if (params.result) searchParams.set('result', params.result)
  searchParams.set('page', String(params.page || 1))
  searchParams.set('page_size', String(params.page_size || 20))
  const res = await fetch(`/api/v1/hr/contracts/approval-results?${searchParams.toString()}`, { cache: 'no-store' })
  if (!res.ok) throw new Error('获取合同审批结果失败')
  return res.json()
}

export async function exportContractApprovalResults(params: Omit<ContractApprovalResultQuery, 'page' | 'page_size'> = {}): Promise<Blob> {
  const searchParams = new URLSearchParams()
  if (params.start_date) searchParams.set('start_date', params.start_date)
  if (params.end_date) searchParams.set('end_date', params.end_date)
  if (params.department) searchParams.set('department', params.department)
  if (params.result) searchParams.set('result', params.result)
  const res = await fetch(`/api/v1/hr/contracts/approval-results/export?${searchParams.toString()}`, { cache: 'no-store' })
  if (!res.ok) throw new Error('导出合同审批结果失败')
  return res.blob()
}
