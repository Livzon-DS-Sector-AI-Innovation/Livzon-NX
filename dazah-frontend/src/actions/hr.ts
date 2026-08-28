'use server'

import { revalidatePath } from 'next/cache'
import { cookies } from 'next/headers'
import type { components } from '@/types/generated/schema'
import { filenameFromDisposition } from '@/lib/download'
import {
  EmployeeCreateInput,
  EmployeeUpdateInput,
  EmployeeListResponse,
  EmployeeResponse,
  Candidate,
  DepartmentCreateInput,
  DepartmentUpdateInput,
  DepartmentListResponse,
  TeamCreateInput,
  TeamUpdateInput,
  TeamListResponse,
  OffboardingRecordCreateInput,
  OffboardingRecordUpdateInput,
  OffboardingRecordListResponse,
  DepartureRecordListResponse,
  TrainingLedgerCreateInput,
  TrainingLedgerUpdateInput,
  TrainingLedgerRecord,
  TrainerCreateInput,
  TrainerUpdateInput,
  TrainingEvaluationCreateInput,
  TrainingEvaluationUpdateInput,
  PositionTrainingListCreateInput,
  PositionTrainingListUpdateInput,
  PlanTrackingRecordCreateInput,
  PlanTrackingRecordUpdateInput,
  NewEmployeeTrainingPlanGenerateInput,
  NewEmployeeTrainingUpdateInput,
  NewEmployeeTrainingItemAddInput,
  NewEmployeeTrainingStartInput,
  NewEmployeeTrainingManualAddInput,
  PositionTrainingMappingCreateInput,
  AnnualTrainingPlanListResponse,
} from '@/types/hr'

const API_BASE =
  process.env.API_BASE_URL ||
  process.env.INTERNAL_API_BASE_URL ||
  'http://dazah-backend-app-1:8000'


async function authedFetch(input: string | URL | Request, init?: RequestInit): Promise<Response> {
  const cookieStore = await cookies()
  const token = cookieStore.get('auth_token')?.value
  const headers: Record<string, string> = {
    ...(init?.headers as Record<string, string> | undefined),
  }
  if (token && !Object.keys(headers).some((h) => h.toLowerCase() === 'authorization')) {
    headers['Authorization'] = `Bearer ${token}`
  }
  return fetch(input, { ...init, headers })
}

export async function fetchEmployeesAction(
  params?: {
    department?: string
    sub_department?: string
    status?: string
    keyword?: string
    gender?: string
    level?: string
    position?: string
    page?: number
    page_size?: number
  }
): Promise<EmployeeListResponse> {
  const searchParams = new URLSearchParams()
  if (params?.department) searchParams.set('department', params.department)
  if (params?.sub_department) searchParams.set('sub_department', params.sub_department)
  if (params?.status) searchParams.set('status', params.status)
  if (params?.keyword) searchParams.set('keyword', params.keyword)
  if (params?.gender) searchParams.set('gender', params.gender)
  if (params?.level) searchParams.set('level', params.level)
  if (params?.position) searchParams.set('position', params.position)
  searchParams.set('page', String(params?.page || 1))
  searchParams.set('page_size', String(params?.page_size || 20))

  const res = await authedFetch(`${API_BASE}/api/v1/hr/employees?${searchParams.toString()}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取员工列表失败')
  return res.json()
}

export async function createEmployee(data: EmployeeCreateInput) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/employees`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || '创建员工失败')
  }
  revalidatePath('/hr/profile')
  return res.json()
}

export async function updateEmployee(id: string, data: EmployeeUpdateInput) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/employees/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || '更新员工失败')
  }
  const result = await res.json()
  revalidatePath('/hr/profile')
  return result
}

export async function deleteEmployee(id: string) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/employees/${id}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || '删除员工失败')
  }
  const result = await res.json()
  revalidatePath('/hr/profile')
  return result
}

// ─── Feishu Sync Actions ───

export async function syncFromFeishuAction() {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/employees/sync-from-feishu`, {
    method: 'POST',
    cache: 'no-store',
    signal: AbortSignal.timeout(120000),  // 2分钟超时
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || '从飞书同步失败')
  }
  revalidatePath('/hr/profile')
  return res.json()
}

export async function syncToFeishuAction(id: string) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/employees/${id}/sync-to-feishu`, {
    method: 'POST',
    cache: 'no-store',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || '同步到飞书失败')
  }
  revalidatePath('/hr/profile')
  return res.json()
}

// ─── Department Actions ───

export async function fetchDepartmentsAction(
  params?: {
    keyword?: string
    parent_id?: string
    leader_name?: string
    page?: number
    page_size?: number
  }
): Promise<DepartmentListResponse> {
  const searchParams = new URLSearchParams()
  if (params?.keyword) searchParams.set('keyword', params.keyword)
  if (params?.parent_id) searchParams.set('parent_id', params.parent_id)
  if (params?.leader_name) searchParams.set('leader_name', params.leader_name)
  searchParams.set('page', String(params?.page || 1))
  searchParams.set('page_size', String(params?.page_size || 100))

  const res = await authedFetch(`${API_BASE}/api/v1/hr/departments?${searchParams.toString()}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取部门列表失败')
  return res.json()
}

export async function createDepartment(data: DepartmentCreateInput) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/departments`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || '创建部门失败')
  }
  revalidatePath('/hr/departments')
  return res.json()
}

export async function updateDepartment(id: string, data: DepartmentUpdateInput) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/departments/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || '更新部门失败')
  }
  revalidatePath('/hr/departments')
  return res.json()
}

export async function deleteDepartment(id: string) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/departments/${id}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || '删除部门失败')
  }
  revalidatePath('/hr/departments')
  return res.json()
}

// ─── Team Actions ───

export async function fetchTeamsAction(
  params?: {
    department_id?: string
    keyword?: string
    page?: number
    page_size?: number
  }
): Promise<TeamListResponse> {
  const searchParams = new URLSearchParams()
  if (params?.department_id) searchParams.set('department_id', params.department_id)
  if (params?.keyword) searchParams.set('keyword', params.keyword)
  searchParams.set('page', String(params?.page || 1))
  searchParams.set('page_size', String(params?.page_size || 100))

  const res = await authedFetch(`${API_BASE}/api/v1/hr/teams?${searchParams.toString()}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取班组列表失败')
  return res.json()
}

export async function createTeam(data: TeamCreateInput) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/teams`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || '创建班组失败')
  }
  revalidatePath('/hr/departments')
  return res.json()
}

export async function updateTeam(id: string, data: TeamUpdateInput) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/teams/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || '更新班组失败')
  }
  revalidatePath('/hr/departments')
  return res.json()
}

export async function deleteTeam(id: string) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/teams/${id}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || '删除班组失败')
  }
  revalidatePath('/hr/departments')
  return res.json()
}

// ─── OffboardingRecord Actions ───

export async function fetchOffboardingRecordsAction(
  params?: {
    employee_id?: string
    keyword?: string
    page?: number
    page_size?: number
  }
): Promise<OffboardingRecordListResponse> {
  const searchParams = new URLSearchParams()
  if (params?.employee_id) searchParams.set('employee_id', params.employee_id)
  if (params?.keyword) searchParams.set('keyword', params.keyword)
  searchParams.set('page', String(params?.page || 1))
  searchParams.set('page_size', String(params?.page_size || 20))

  const res = await authedFetch(`${API_BASE}/api/v1/hr/offboarding-records?${searchParams.toString()}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取离职记录失败')
  return res.json()
}

export async function createOffboardingRecord(data: OffboardingRecordCreateInput) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/offboarding-records`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || '创建离职记录失败')
  }
  revalidatePath('/hr/offboarding')
  revalidatePath('/hr/profile')
  return res.json()
}

export async function updateOffboardingRecord(id: string, data: OffboardingRecordUpdateInput) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/offboarding-records/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || '更新离职记录失败')
  }
  revalidatePath('/hr/offboarding')
  return res.json()
}

export async function deleteOffboardingRecord(id: string) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/offboarding-records/${id}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || '删除离职记录失败')
  }
  revalidatePath('/hr/offboarding')
  return res.json()
}

// ─── Annual Training Plan Actions ───

export async function createAnnualTrainingPlan(data: { year: number; department: string; plan_level?: string }) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/annual-training-plans`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('创建年度培训计划失败')
  revalidatePath('/hr/training/annual-plan')
  return res.json()
}

export async function deleteAnnualTrainingPlan(id: string) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/annual-training-plans/${id}`, {
    method: 'DELETE',
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('删除年度培训计划失败')
  revalidatePath('/hr/training/annual-plan')
  return res.json()
}

export async function batchUpdatePlanItems(planId: string, data: { items: unknown[] }) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/annual-training-plans/${planId}/items/batch`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('批量更新计划明细失败')
  revalidatePath('/hr/training/annual-plan')
  return res.json()
}

export async function importAnnualTrainingPlan(
  file: File,
  year: number,
  planLevel?: string,
  department?: string
): Promise<{ code: number; message: string; data: unknown }> {
  const formData = new FormData()
  formData.append('file', file)

  const params = new URLSearchParams({
    year: String(year),
  })
  // 计划级别和部门留空时，后端会从文档内容自动识别（APP1→部门级、APP2→公司级）
  if (planLevel) params.set('plan_level', planLevel)
  if (department) params.set('department', department)

  const res = await authedFetch(`${API_BASE}/api/v1/hr/annual-training-plans/import?${params}`, {
    method: 'POST',
    body: formData,
    cache: 'no-store',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || err.message || '导入失败')
  }
  revalidatePath('/hr/training/annual-plan')
  return res.json()
}

// ─── STUB: Candidate/Recruitment Actions (not yet implemented) ───

export async function createCandidateAction(formData: FormData) {
  throw new Error('createCandidateAction: 功能尚未实现')
}

export async function parseResumePreviewAction(_formData: FormData): Promise<{
  data: { gender: string; school: string; education: string; major: string; match_report: string; recommendation_level: string }
}> {
  throw new Error('parseResumePreviewAction: 功能尚未实现')
}

export async function syncCandidateToFeishuAction(candidateId: string) {
  throw new Error('syncCandidateToFeishuAction: 功能尚未实现')
}

export async function updateCandidateAction(candidateId: string, data: unknown) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/candidates/${candidateId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || '更新候选人失败')
  }
  revalidatePath('/hr/recruitment')
  return res.json()
}

export async function updateCandidateRecommendationLevelAction(candidateId: string, level: string) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/candidates/${candidateId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ fit_level: level }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || '更新推荐等级失败')
  }
  revalidatePath('/hr/recruitment')
  return res.json()
}

export async function fetchCandidatesFromFeishu() {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/candidates/sync-from-feishu`, {
    method: 'GET',
    cache: 'no-store',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || '同步候选人失败')
  }
  revalidatePath('/hr/recruitment')
  return res.json()
}

export async function deleteCandidateAction(candidateId: string) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/candidates/${candidateId}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || '删除候选人失败')
  }
  revalidatePath('/hr/recruitment')
  return res.json()
}

// ─── Server-side fetch functions (for Server Components) ───

export async function fetchEmployees(
  params?: {
    department?: string
    status?: string
    keyword?: string
    page?: number
    page_size?: number
  }
): Promise<EmployeeListResponse> {
  return fetchEmployeesAction(params)
}

export async function fetchDepartments(
  params?: {
    keyword?: string
    page?: number
    page_size?: number
  }
): Promise<DepartmentListResponse> {
  return fetchDepartmentsAction(params)
}

export async function fetchOffboardingRecords(
  params?: {
    employee_id?: string
    keyword?: string
    page?: number
    page_size?: number
  }
): Promise<OffboardingRecordListResponse> {
  return fetchOffboardingRecordsAction(params)
}

export async function fetchDepartureRecords(
  params?: {
    department?: string
    offboarding_type?: string
    keyword?: string
    sort_by?: string
    sort_order?: string
    page?: number
    page_size?: number
  }
): Promise<DepartureRecordListResponse> {
  const searchParams = new URLSearchParams()
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== '') searchParams.set(key, String(value))
  })
  if (!searchParams.has('page')) searchParams.set('page', '1')
  if (!searchParams.has('page_size')) searchParams.set('page_size', '20')
  const res = await authedFetch(`${API_BASE}/api/v1/hr/departure-records?${searchParams.toString()}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取离职台账记录失败')
  return res.json()
}

// fetchTeams 复用 fetchTeamsAction（避免重复实现）
export const fetchTeams = fetchTeamsAction

export async function fetchEmployeeById(id: string): Promise<EmployeeResponse> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/employees/${id}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取员工详情失败')
  return res.json()
}

export async function fetchCandidateById(id: string): Promise<{ code: number; message: string; data: Candidate }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/candidates/${id}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取候选人详情失败')
  return res.json()
}

export async function fetchAnnualTrainingPlanById(id: string): Promise<AnnualTrainingPlanListResponse> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/annual-training-plans/${id}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取年度培训计划详情失败')
  return res.json()
}

export async function fetchPlanItems(id: string): Promise<{ code: number; message: string; data: unknown[]; meta?: { total: number } }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/annual-training-plans/${id}/items`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取年度计划明细失败')
  return res.json()
}

export async function fetchEmployeeByNumber(employeeNumber: string): Promise<EmployeeResponse> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/employees/by-number/${employeeNumber}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取员工详情失败')
  return res.json()
}

// ─── Department Tree Actions ───

import { Department } from '@/types/hr'

export async function fetchDepartmentTreeAction(): Promise<{ code: number; message: string; data: Department[] }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/departments/tree`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取部门树失败')
  return res.json()
}

export async function syncDepartmentsFromFeishuAction(forceRefresh = true): Promise<{ code: number; message: string; data: { task_id: string; state: string } }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/departments/sync-from-feishu?force_refresh=${forceRefresh}`, {
    method: 'POST',
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('从飞书同步部门失败')
  return res.json()
}

export async function getDepartmentSyncStatus(): Promise<{ code: number; message: string; data: { state: string; progress: string; result: unknown } }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/departments/sync-status`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('查询同步状态失败')
  return res.json()
}

// ─── HR 飞书设置 Server Actions ───

async function hrActionFetch<T>(url: string, options?: RequestInit): Promise<T | null> {
  const cookieStore = await cookies()
  const authToken = cookieStore.get('auth_token')?.value
  const response = await authedFetch(url, {
    ...options,
    headers: {
      ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
      ...(options?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...options?.headers,
    },
  })
  if (!response.ok) {
    const errorBody = await response.text().catch(() => '')
    let errorMessage = `请求失败: ${response.status} ${response.statusText}`
    try {
      const errorJson = JSON.parse(errorBody)
      if (errorJson.detail) errorMessage = typeof errorJson.detail === 'string' ? errorJson.detail : JSON.stringify(errorJson.detail)
      else if (errorJson.message) errorMessage = errorJson.message
    } catch {}
    throw new Error(errorMessage)
  }
  if (response.status === 204) return null
  const result = await response.json()
  return result.data
}

export async function updateHrFeishuAppSettings(data: { app_id: string; app_secret: string; is_enabled: boolean }): Promise<unknown> {
  return hrActionFetch(`${API_BASE}/api/v1/hr/feishu-settings/app`, { method: 'PUT', body: JSON.stringify(data) })
}

export async function testHrFeishuAppSettings(): Promise<unknown> {
  return hrActionFetch(`${API_BASE}/api/v1/hr/feishu-settings/app/test`, { method: 'POST' })
}

export async function updateHrFeishuEntitySetting(entityCode: string, data: unknown): Promise<unknown> {
  return hrActionFetch(`${API_BASE}/api/v1/hr/feishu-settings/entities/${entityCode}`, { method: 'PUT', body: JSON.stringify(data) })
}

export async function testHrFeishuEntitySetting(entityCode: string): Promise<unknown> {
  return hrActionFetch(`${API_BASE}/api/v1/hr/feishu-settings/entities/${entityCode}/test`, { method: 'POST' })
}

// ─── 邮箱配置 ───

export async function updateEmailConfig(data: Record<string, unknown>) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/email/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.message || '更新失败') }
  return res.json()
}

export async function testEmailConfig() {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/email/config/test`, { method: 'POST' })
  if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.message || '测试失败') }
  return res.json()
}

// ─── 提醒/审批配置 ───

export async function updateReminderConfig(configId: string, data: unknown) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/hr-settings/reminders/${configId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error('保存提醒配置失败')
  revalidatePath('/hr/settings/reminder')
  return (await res.json()).data
}

export async function updateApprovalConfig(configId: string, data: unknown) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/hr-settings/approvals/${configId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error('保存审批配置失败')
  revalidatePath('/hr/settings/approval')
  return (await res.json()).data
}

export async function saveDeptRecipients(configId: string, data: Array<unknown>) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/hr-settings/reminders/${configId}/dept-recipients`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error('保存部门接收人配置失败')
  revalidatePath('/hr/settings/reminder')
  return (await res.json()).data
}

export async function deleteDeptRecipient(deptRecipientId: string) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/hr-settings/dept-recipients/${deptRecipientId}`, { method: 'DELETE' })
  if (!res.ok) throw new Error('删除部门接收人配置失败')
  revalidatePath('/hr/settings/reminder')
  return true
}

// ─── 飞书联系人同步 ───

export async function syncFeishuMembersAction(): Promise<{ code: number; message: string; data: unknown }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/hr-settings/hr-members/sync`, {
    method: 'POST',
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('同步飞书联系人失败')
  return res.json()
}

export async function getFeishuMembersSyncStatus(): Promise<{ code: number; message: string; data: { state: string; progress: string; result: unknown } }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/hr-settings/hr-members/sync-status`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('查询同步状态失败')
  return res.json()
}

// ─── 服务端 GET 函数 ───

export async function fetchJobPostingsServer(params?: { keyword?: string; page?: number; page_size?: number }) {
  const sp = new URLSearchParams()
  if (params?.keyword) sp.set('keyword', params.keyword)
  sp.set('page', String(params?.page || 1))
  sp.set('page_size', String(params?.page_size || 100))
  const res = await authedFetch(`${API_BASE}/api/v1/hr/jobs?${sp.toString()}`, { cache: 'no-store' })
  if (!res.ok) throw new Error('获取职位列表失败')
  return res.json()
}

export async function fetchOrgTreeAction() {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/departments/org-tree`, { cache: 'no-store' })
  if (!res.ok) throw new Error('获取组织架构树失败')
  return res.json()
}

// ─── 招聘管理 Actions ───

export async function createJobPosting(data: unknown) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.message || '创建职位失败') }
  revalidatePath('/hr/recruitment')
  return res.json()
}

export async function batchAnalyzeCandidatesAction(candidateIds: string[]) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/candidates/ai-analyze-batch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ candidate_ids: candidateIds }),
  })
  if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.message || '批量分析失败') }
  revalidatePath('/hr/recruitment')
  return res.json()
}

export async function createOnboardingFromInterviewAction(candidateId: string) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/onboarding/from-interview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ candidate_id: candidateId }),
  })
  if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.message || '转入职失败') }
  revalidatePath('/hr/recruitment')
  return res.json()
}

export async function updateOnboardingAction(id: string, data: unknown) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/onboarding/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.message || '更新入职信息失败') }
  return res.json()
}

export async function createEmployeePublicAction(data: Record<string, unknown>) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/employees/public-create`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || '提交失败')
  }
  return res.json()
}

export async function syncOnboardingToEmployeeAction(recordId: string) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/onboarding/${recordId}/sync-to-employee`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })
  if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.message || '同步到员工档案失败') }
  return res.json()
}

export async function syncOnboardingToContractAction(name?: string, department?: string, level?: string) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/contracts/sync-from-onboarding`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, department, level }),
  })
  if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.message || '同步到合同管理失败') }
  return res.json()
}

export async function triggerEmailFetch(scanAll: boolean = true) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/email/fetch-now`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scan_all: scanAll }),
  })
  if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.message || '抓取失败') }
  return res.json()
}

// ─── 岗位调动审批 ───

export async function submitPositionTransferApproval(
  id: string,
  isSupervisorLevel: boolean,
  customApprovers?: Record<string, string>,
) {
  const body: Record<string, unknown> = { is_supervisor_level: isSupervisorLevel }
  if (customApprovers && Object.keys(customApprovers).length > 0) {
    body.custom_approvers = customApprovers
  }
  const res = await authedFetch(`${API_BASE}/api/v1/hr/position-transfers/${id}/submit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.message || err.detail || '提交审批失败') }
  revalidatePath('/hr/position-transfer')
  return res.json()
}

export async function approvePositionTransferNode(id: string, opinion: string) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/position-transfers/${id}/approve-node`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ opinion }),
  })
  if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.message || err.detail || '审批失败') }
  revalidatePath('/hr/position-transfer')
  return res.json()
}

export async function rejectPositionTransferNode(id: string, opinion: string) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/position-transfers/${id}/reject-node`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ opinion }),
  })
  if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.message || err.detail || '拒绝失败') }
  revalidatePath('/hr/position-transfer')
  return res.json()
}

export async function createPositionTransfer(data: unknown) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/position-transfers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error('创建调动失败')
  revalidatePath('/hr/position-transfer')
  return res.json()
}

export async function updatePositionTransfer(id: string, data: unknown) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/position-transfers/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error('更新调动失败')
  revalidatePath('/hr/position-transfer')
  return res.json()
}

export async function deletePositionTransfer(id: string) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/position-transfers/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error('删除调动失败')
  revalidatePath('/hr/position-transfer')
  return res.json()
}

export async function syncPositionTransferFromFeishuAction() {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/position-transfers/sync-from-feishu`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error('同步飞书失败')
  revalidatePath('/hr/position-transfer')
  return res.json()
}

// ─── 部门级审批人配置 ───

export async function createDeptApprovalConfigAction(data: {
  department_id: string
  department_name: string
  direct_leader_name?: string
  direct_leader_open_id?: string
  manager_name?: string
  manager_open_id?: string
  director_name?: string
  director_open_id?: string
  vp_name?: string
  vp_open_id?: string
}) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/dept-approval-configs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.message || '创建失败') }
  revalidatePath('/hr/settings/approval')
  return res.json()
}

export async function updateDeptApprovalConfigAction(id: string, data: Record<string, unknown>) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/dept-approval-configs/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.message || '更新失败') }
  revalidatePath('/hr/settings/approval')
  return res.json()
}

export async function deleteDeptApprovalConfigAction(id: string) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/dept-approval-configs/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error('删除失败')
  revalidatePath('/hr/settings/approval')
  return res.json()
}

export async function initDeptApprovalConfigsAction() {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/dept-approval-configs/init-from-departments`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error('初始化失败')
  revalidatePath('/hr/settings/approval')
  return res.json()
}

export async function syncOffboardingFromFeishuAction(): Promise<{ code: number; message: string; data: { created: number; updated: number; failed: number; total: number } }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/offboarding-records/sync-from-feishu`, {
    method: 'POST',
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('从飞书同步离职管理数据失败')
  revalidatePath('/hr/offboarding')
  return res.json()
}

export async function generateOffboardingCertificateAction(
  recordId: string
): Promise<{ bytes: ArrayBuffer; filename: string }> {
  const { bytes, disposition } = await fetchDocBytes(
    `${API_BASE}/api/v1/hr/offboarding-records/${recordId}/certificate`,
    {},
    '生成离职证明失败',
  )
  return {
    bytes,
    filename: filenameFromDisposition(disposition, '解除劳动合同通知单.docx'),
  }
}

export async function uploadOffboardingTemplateAction(formData: FormData): Promise<{ code: number; message: string; data: unknown }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/hr-settings/offboarding-template`, {
    method: 'POST',
    body: formData,
    cache: 'no-store',
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || '上传模板失败')
  }
  return res.json()
}

export async function fetchOffboardingTemplateInfoAction(): Promise<{ code: number; message: string; data: { exists: boolean; filename: string | null; updated_at: string | null } }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/hr-settings/offboarding-template`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取模板信息失败')
  return res.json()
}

// ─── TrainingLedger Actions ───

export async function checkTrainingConflict(params: {
  training_date: string
  time_start: string
  time_end: string
  instructor?: string
  trainees: string[]
  exclude_session_id?: string
}) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/training-ledgers/check-conflict`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('冲突检测失败')
  const json = (await res.json()) as components['schemas']['ApiResponseEnvelope_TrainingConflictCheckResponse_']
  const d = json.data ?? {}
  return {
    code: json.code ?? 200,
    message: 'success',
    data: {
      has_conflict: d.has_conflict ?? false,
      instructor_conflicts: (d.instructor_conflicts ?? []).map((x) => ({
        training_name: x.training_name ?? '',
        time_range: x.time_range ?? '',
        conflict_depts: x.conflict_depts ?? [],
        conflict_count: x.conflict_count ?? 0,
      })),
      trainee_conflicts: (d.trainee_conflicts ?? []).map((x) => ({
        training_name: x.training_name ?? '',
        time_range: x.time_range ?? '',
        names: x.names ?? [],
        conflict_count: x.conflict_count ?? 0,
      })),
      suggested_times: (d.suggested_times ?? []).map((x) => ({ start: x.start ?? '', end: x.end ?? '' })),
    },
  }
}

export async function createTrainingLedger(
  data: TrainingLedgerCreateInput
): Promise<{ code: number; message: string; data: TrainingLedgerRecord }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/training-ledgers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('创建培训台账记录失败')
  return res.json()
}

export async function updateTrainingLedger(
  id: string,
  data: TrainingLedgerUpdateInput
): Promise<{ code: number; message: string; data: TrainingLedgerRecord }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/training-ledgers/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('更新培训台账记录失败')
  return res.json()
}

export async function deleteTrainingLedger(
  id: string
): Promise<{ code: number; message: string }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/training-ledgers/${id}`, {
    method: 'DELETE',
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('删除培训台账记录失败')
  return res.json()
}

export async function clearTrainingLedgersByDept(
  department: string
): Promise<{ code: number; message: string; data: { deleted: number } }> {
  const res = await authedFetch(
    `${API_BASE}/api/v1/hr/training-ledgers/by-dept?department=${encodeURIComponent(department)}`,
    { method: 'DELETE', cache: 'no-store' }
  )
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.message || '清空台账失败')
  }
  revalidatePath('/hr/training/ledger')
  return res.json()
}

// ─── TrainingLedgerPage Actions ───

export interface TrainingLedgerPageRecord {
  id: string
  employee_number: string
  employee_name: string
  department?: string
  created_at: string
  updated_at: string
}

export async function createTrainingLedgerPage(
  data: { employee_number: string; employee_name: string }
): Promise<{ code: number; message: string; data: TrainingLedgerPageRecord }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/training-ledgers/pages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('创建培训台账页面失败')
  return res.json()
}

// ─── Training Document Generation Actions ───
// 规范：Server Action 服务端执行，禁止 window/document；返回字节流，浏览器侧用 lib/download.ts 下载

async function fetchDocBytes(url: string, data: unknown, errMsg: string) {
  const res = await authedFetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    cache: 'no-store',
  })
  if (!res.ok) {
    // 带上后端真实报错（校验/模板缺失等），便于定位
    let detail = ''
    try {
      const body = await res.json().catch(() => null)
      detail = body?.message || body?.detail ? JSON.stringify(body?.detail ?? body?.message) : ''
    } catch {
      /* 非 JSON 响应忽略 */
    }
    throw new Error(detail ? `${errMsg}：${detail}` : errMsg)
  }
  const bytes = await res.arrayBuffer()
  return { bytes, disposition: res.headers.get('content-disposition') }
}

export async function generateTrainingSignInSheet(
  data: components['schemas']['TrainingSignInSheetInput']
): Promise<{ bytes: ArrayBuffer; filename: string }> {
  const { bytes, disposition } = await fetchDocBytes(
    `${API_BASE}/api/v1/hr/training-sign-in-sheet`,
    data,
    '生成培训签到表失败',
  )
  return {
    bytes,
    filename: filenameFromDisposition(disposition, `7.5培训签到表_${data.training_date || 'nodate'}.docx`),
  }
}

export async function generateTrainingNotification(
  data: components['schemas']['TrainingNotificationInput']
): Promise<{ bytes: ArrayBuffer; filename: string }> {
  const { bytes, disposition } = await fetchDocBytes(
    `${API_BASE}/api/v1/hr/training-notification`,
    data,
    '生成培训通知失败',
  )
  return {
    bytes,
    filename: filenameFromDisposition(disposition, notificationFilename(data.training_date)),
  }
}

// 培训通知文件名：日期-培训通知.docx（与后端 Content-Disposition 一致）
function notificationFilename(trainingDate?: string | null): string {
  if (!trainingDate) return '培训通知.docx'
  return `${trainingDate}-培训通知.docx`
}

export async function generateTrainingEvaluation(
  data: components['schemas']['TrainingEvaluationInput']
): Promise<{ bytes: ArrayBuffer; filename: string }> {
  const { bytes, disposition } = await fetchDocBytes(
    `${API_BASE}/api/v1/hr/training-evaluation`,
    data,
    '生成培训效果评估表失败',
  )
  return {
    bytes,
    filename: filenameFromDisposition(disposition, `APP4培训评估表_${data.training_date || 'nodate'}.docx`),
  }
}

export async function generateOnboardingEvaluation(
  data: components['schemas']['OnboardingEvaluationInput']
): Promise<{ bytes: ArrayBuffer; filename: string }> {
  const { bytes, disposition } = await fetchDocBytes(
    `${API_BASE}/api/v1/hr/onboarding-evaluation`,
    data,
    '生成员工上岗评估表失败',
  )
  return {
    bytes,
    filename: filenameFromDisposition(disposition, `7.12员工上岗评估表_${data.approval_date || 'nodate'}.xlsx`),
  }
}

export async function generateOralExamResult(
  data: components['schemas']['OralExamExportRequest']
): Promise<{ bytes: ArrayBuffer; filename: string }> {
  const { bytes, disposition } = await fetchDocBytes(
    `${API_BASE}/api/v1/hr/training-oral-exam/export`,
    data,
    '导出口试考核结果表失败',
  )
  return {
    bytes,
    filename: filenameFromDisposition(disposition, `口试培训考核结果表_${data.training_date || 'nodate'}.docx`),
  }
}

export async function generatePracticalExamResult(
  data: components['schemas']['PracticalExamExportRequest']
): Promise<{ bytes: ArrayBuffer; filename: string }> {
  const { bytes, disposition } = await fetchDocBytes(
    `${API_BASE}/api/v1/hr/training-practical-exam/export`,
    data,
    '导出实操考核结果表失败',
  )
  return {
    bytes,
    filename: filenameFromDisposition(disposition, `${data.training_date || 'nodate'}-${data.training_content || ''}-实操.zip`),
  }
}

export async function generateTrainingAttachment(
  data: components['schemas']['TrainingAttachmentExportRequest']
): Promise<{ bytes: ArrayBuffer; filename: string }> {
  const { bytes, disposition } = await fetchDocBytes(
    `${API_BASE}/api/v1/hr/training-attachment`,
    data,
    '生成培训附件失败',
  )
  return {
    bytes,
    filename: filenameFromDisposition(disposition, '培训附件.docx'),
  }
}

/** 导入实操试题（APP13 格式 docx），返回提取的实操考核情况描述与培训日期 */
export async function importPracticalExamQuestions(
  file: File
): Promise<{ code: number; message: string; data: { description: string; training_date: string } }> {
  const formData = new FormData()
  formData.append('file', file)
  const res = await authedFetch(`${API_BASE}/api/v1/hr/training-practical-exam/import`, {
    method: 'POST',
    body: formData,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.message || '导入实操试题失败')
  }
  return res.json()
}

// ─── Feishu Sync Actions (migrated from lib/api/hr.ts) ───


export async function syncContractsFromFeishu(): Promise<{ code: number; message: string; data: { created: number; updated: number; total: number } }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/contracts/sync-from-feishu`, {
    method: 'POST',
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('从飞书同步合同管理失败')
  return res.json()
}

// ─── 合同到期提醒 Actions ───

export async function pushContractExpiringAction(
  startDate: string,
  endDate: string
): Promise<{ code: number; message: string; data: unknown }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/employees/contract-expiring/push-notify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ start_date: startDate, end_date: endDate }),
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('触发合同到期提醒失败')
  return res.json()
}

export async function getContractPushStatusAction(): Promise<{ code: number; data: unknown }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/employees/contract-expiring/push-status`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取推送状态失败')
  return res.json()
}

export async function saveContractTemplateAction(payload: Record<string, unknown>): Promise<{ code: number; message: string }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/employees/contract-expiring/template`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('保存模板失败')
  return res.json()
}

export async function deleteContractAction(id: string): Promise<{ code: number; message: string }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/contracts/${id}`, {
    method: 'DELETE',
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('删除合同失败')
  revalidatePath('/hr/contracts')
  return res.json()
}

export async function updateContractAction(
  id: string,
  data: Record<string, unknown>
): Promise<{ code: number; message: string; data: unknown }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/contracts/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('更新合同失败')
  revalidatePath('/hr/contracts')
  return res.json()
}

export async function renewContractAction(
  id: string,
  startDate: string,
  endDate: string
): Promise<{ code: number; message: string; data: unknown }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/contracts/${id}/renew`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ start_date: startDate, end_date: endDate }),
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('续签失败')
  revalidatePath('/hr/contracts')
  revalidatePath('/hr/profile')
  return res.json()
}

// ═══════════════════════════════════════════════════════════════
// 培训管理二次开发新增 Server Actions（SMP-HR-002-14）
// ═══════════════════════════════════════════════════════════════

// ─── 培训师管理 ───

export async function createTrainer(
  data: TrainerCreateInput
): Promise<{ code: number; message: string; data: unknown }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/trainers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('创建培训师失败')
  revalidatePath('/hr/training/trainer')
  return res.json()
}

export async function updateTrainer(
  id: string,
  data: TrainerUpdateInput
): Promise<{ code: number; message: string; data: unknown }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/trainers/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('更新培训师失败')
  revalidatePath('/hr/training/trainer')
  return res.json()
}

export async function deleteTrainer(
  id: string
): Promise<{ code: number; message: string }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/trainers/${id}`, {
    method: 'DELETE',
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('删除培训师失败')
  revalidatePath('/hr/training/trainer')
  return res.json()
}

export async function importTrainers(
  formData: FormData
): Promise<{ code: number; message: string; data: unknown }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/trainers/import`, {
    method: 'POST',
    body: formData,
    cache: 'no-store',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || err.message || '导入培训师失败')
  }
  revalidatePath('/hr/training/trainer')
  return res.json()
}

// ─── 培训评估表 ───

export async function createTrainingEvaluation(
  data: TrainingEvaluationCreateInput
): Promise<{ code: number; message: string; data: unknown }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/training-evaluations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('创建培训评估表失败')
  revalidatePath('/hr/training/sign-in')
  return res.json()
}

export async function updateTrainingEvaluation(
  id: string,
  data: TrainingEvaluationUpdateInput
): Promise<{ code: number; message: string; data: unknown }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/training-evaluations/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('更新培训评估表失败')
  revalidatePath('/hr/training/sign-in')
  return res.json()
}

export async function deleteTrainingEvaluation(
  id: string
): Promise<{ code: number; message: string }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/training-evaluations/${id}`, {
    method: 'DELETE',
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('删除培训评估表失败')
  revalidatePath('/hr/training/sign-in')
  return res.json()
}

// ─── 培训人员配置 ───

export async function saveTrainingPersonnelConfig(
  data: components['schemas']['TrainingPersonnelConfigCreate']
): Promise<{ code: number; message: string; data: unknown }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/training-personnel-configs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('保存培训人员配置失败')
  revalidatePath('/hr/training/sign-in')
  return res.json()
}

export async function deleteTrainingPersonnelConfig(
  configId: string
): Promise<{ code: number; message: string }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/training-personnel-configs/${configId}`, {
    method: 'DELETE',
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('删除培训人员配置失败')
  return res.json()
}

// ─── 岗位培训清单 ───

export async function createPositionTrainingList(
  data: PositionTrainingListCreateInput
): Promise<{ code: number; message: string; data: unknown }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/position-training-lists`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('创建岗位培训清单失败')
  revalidatePath('/hr/training/position-training')
  return res.json()
}

export async function updatePositionTrainingList(
  id: string,
  data: PositionTrainingListUpdateInput
): Promise<{ code: number; message: string; data: unknown }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/position-training-lists/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('更新岗位培训清单失败')
  revalidatePath('/hr/training/position-training')
  return res.json()
}

export async function deletePositionTrainingList(
  id: string
): Promise<{ code: number; message: string }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/position-training-lists/${id}`, {
    method: 'DELETE',
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('删除岗位培训清单失败')
  revalidatePath('/hr/training/position-training')
  return res.json()
}

// ─── 岗位培训清单导入 ───

export async function batchUpdatePositionTrainingListItems(
  listId: string,
  items: Array<{
    level: string
    sort_order?: number
    textbook_name?: string
    textbook_code?: string
    assessment_method?: string
    remarks?: string
  }>
): Promise<{ code: number; message: string; data: unknown }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/position-training-lists/${listId}/items/batch`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items }),
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('批量更新明细失败')
  revalidatePath('/hr/training/position-training')
  return res.json()
}

export async function importPositionTrainingLists(
  file: File,
): Promise<{ code: number; message: string; data: unknown }> {
  const formData = new FormData()
  formData.append('file', file)
  const res = await authedFetch(`${API_BASE}/api/v1/hr/position-training-lists/import`, {
    method: 'POST',
    body: formData,
    cache: 'no-store',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || err.detail || '导入岗位培训清单失败')
  }
  revalidatePath('/hr/training/position-training')
  return res.json()
}

export async function clearPositionTrainingListsByDept(
  department: string
): Promise<{ code: number; message: string; data: unknown }> {
  const res = await authedFetch(
    `${API_BASE}/api/v1/hr/position-training-lists/by-dept/clear?department=${encodeURIComponent(department)}`,
    { method: 'DELETE', cache: 'no-store' },
  )
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || err.detail || '清除失败')
  }
  revalidatePath('/hr/training/position-training')
  return res.json()
}

// ─── 培训计划跟踪 ───

export async function createPlanTrackingRecord(
  data: PlanTrackingRecordCreateInput
): Promise<{ code: number; message: string; data: unknown }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/plan-tracking`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('创建培训计划跟踪记录失败')
  revalidatePath('/hr/training/plan-tracking')
  return res.json()
}

export async function updatePlanTrackingRecord(
  id: string,
  data: PlanTrackingRecordUpdateInput
): Promise<{ code: number; message: string; data: unknown }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/plan-tracking/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('更新培训计划跟踪记录失败')
  revalidatePath('/hr/training/plan-tracking')
  return res.json()
}

export async function deletePlanTrackingRecord(
  id: string
): Promise<{ code: number; message: string }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/plan-tracking/${id}`, {
    method: 'DELETE',
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('删除培训计划跟踪记录失败')
  revalidatePath('/hr/training/plan-tracking')
  return res.json()
}

// ─── ESG 培训报表 ───

export async function updateEsgTrainingRecord(
  id: string,
  data: Record<string, unknown>
): Promise<void> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/esg-training-records/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error('更新ESG培训记录失败')
}

export async function deleteEsgTrainingRecord(
  id: string
): Promise<void> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/esg-training-records/${id}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error('删除ESG培训记录失败')
}

export async function syncEsgFromLedger(department: string): Promise<{
  code: number
  message: string
  data: {
    created: number
    skipped: number
    skipped_existing: number
    skipped_unmatched: number
    skipped_other_dept: number
  }
}> {
  const sp = new URLSearchParams({ department })
  const res = await authedFetch(
    `${API_BASE}/api/v1/hr/esg-training-records/sync-from-ledger?${sp}`,
    {
      method: 'POST',
      cache: 'no-store',
    }
  )
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.message || '同步失败')
  }
  return res.json()
}

export async function importTrainingLedgerByDept(
  file: File,
  department: string
): Promise<{ code: number; message: string; data: unknown }> {
  const formData = new FormData()
  formData.append('file', file)
  const res = await authedFetch(
    `${API_BASE}/api/v1/hr/training-ledgers/import-by-dept?department=${encodeURIComponent(department)}`,
    { method: 'POST', body: formData }
  )
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.message || '导入培训台账失败')
  }
  return res.json()
}

export async function importEsgRecordsByDept(
  file: File,
  department: string
): Promise<{ code: number; message: string; data: unknown }> {
  const formData = new FormData()
  formData.append('file', file)
  const res = await authedFetch(
    `${API_BASE}/api/v1/hr/esg-training-records/import?department=${encodeURIComponent(department)}`,
    { method: 'POST', body: formData }
  )
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.message || '导入ESG培训记录失败')
  }
  return res.json()
}

// ─── AI 智能导入（预览分析 + 确认导入）───

export async function previewTrainingImport(
  file: File,
  department: string
): Promise<{
  code: number
  message: string
  data: components['schemas']['ImportPreviewData']
}> {
  const formData = new FormData()
  formData.append('file', file)
  const res = await authedFetch(
    `${API_BASE}/api/v1/hr/training-ledgers/import-preview?department=${encodeURIComponent(department)}`,
    { method: 'POST', body: formData }
  )
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.message || '文件分析失败')
  }
  return res.json()
}

export async function confirmTrainingImport(
  file: File,
  department: string,
  sheets: components['schemas']['ImportSheetConfirm'][]
): Promise<{ code: number; message: string; data: unknown }> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('department', department)
  formData.append('sheets', JSON.stringify(sheets))
  const res = await authedFetch(`${API_BASE}/api/v1/hr/training-ledgers/import-confirm`, {
    method: 'POST',
    body: formData,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.message || '导入失败')
  }
  revalidatePath('/hr/training/ledger')
  return res.json()
}

// ─── 笔试成绩导入 ───

export async function importExamScores(
  file: File,
  recordId: string
): Promise<{ code: number; message: string; data: { name: string; score: string }[] }> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('record_id', recordId)
  const res = await authedFetch(`${API_BASE}/api/v1/hr/training-ledgers/import-exam-scores`, {
    method: 'POST',
    body: formData,
    cache: 'no-store',
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.message || '解析成绩文件失败')
  }
  return res.json()
}

export async function confirmExamScores(
  recordId: string,
  scores: { name: string; score: string }[]
): Promise<{ code: number; message: string; data: { synced_count: number; score_summary: string } }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/training-ledgers/confirm-exam-scores`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ record_id: recordId, scores }),
    cache: 'no-store',
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.message || '确认导入成绩失败')
  }
  revalidatePath('/hr/training/ledger')
  return res.json()
}

// ─── 年度培训计划附件 ───

export async function uploadPlanAttachments(
  planId: string,
  files: File[]
): Promise<{ code: number; message: string; data: unknown }> {
  const formData = new FormData()
  for (const f of files) {
    formData.append('files', f)
  }
  const res = await authedFetch(`${API_BASE}/api/v1/hr/annual-training-plans/${planId}/attachments`, {
    method: 'POST',
    body: formData,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.message || '上传附件失败')
  }
  return res.json()
}

export async function deletePlanAttachment(
  attachmentId: string
): Promise<{ code: number; message: string }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/annual-training-plan-attachments/${attachmentId}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error('删除附件失败')
  return res.json()
}

/** 保存/更新培训会话，返回 session_id */
export async function upsertTrainingSession(
  data: components['schemas']['TrainingSessionUpsert'],
): Promise<string> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/training-sessions/upsert`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('保存培训会话失败')
  const json = await res.json()
  return json.data?.id
}

/** 保存会话资料（同会话同类覆盖更新），返回资料 ID */
export async function upsertTrainingDocument(
  data: components['schemas']['TrainingDocumentUpsert'],
): Promise<string> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/training-documents/upsert`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('保存培训资料失败')
  const json = await res.json()
  return json.data?.id
}

/** 标记附件文件清单条目已培训（置灰不可再选） */
export async function markTrainingContentUsed(
  items: { name: string; code?: string | null; attachment_id?: string | null }[]
): Promise<{ code: number; message: string }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/training-content-used`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items }),
  })
  if (!res.ok) throw new Error('标记文件条目已培训失败')
  return res.json()
}

// ─── 员工培训清单（配置表方案）───

/** 一键导入飞书联系人（department 为空=全部部门一次导入） */
export async function importFeishuMembers(department?: string): Promise<{
  data?: { total?: number; per_department?: Record<string, number> }
  message?: string
}> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/training/employee-training-list/members/import-feishu`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ department: department || null }),
    cache: 'no-store',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || err.detail || '导入飞书联系人失败')
  }
  return res.json()
}

/** 手动添加人员（离职等不在飞书联系人的人员） */
export async function addEmployeeTrainingMember(
  department: string,
  name: string,
  employee_number?: string
): Promise<{ message?: string }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/training/employee-training-list/members`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ department, name, employee_number: employee_number || null }),
    cache: 'no-store',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || err.detail || '添加人员失败')
  }
  return res.json()
}

/** 移除人员 */
export async function removeEmployeeTrainingMember(id: string): Promise<{ message?: string }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/training/employee-training-list/members/${id}`, {
    method: 'DELETE',
    cache: 'no-store',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || err.detail || '移除人员失败')
  }
  return res.json()
}

/** 编辑人员姓名 */
export async function updateEmployeeTrainingMember(
  id: string,
  name: string
): Promise<{ message?: string }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/training/employee-training-list/members/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
    cache: 'no-store',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || err.detail || '编辑人员失败')
  }
  return res.json()
}

/** 标记计划附件已导入培训台账（置灰不可再选） */
export async function markPlanAttachmentsLedgerImported(
  ids: string[]
): Promise<{ code: number; message: string }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/annual-training-plan-attachments/mark-ledger-imported`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  })
  if (!res.ok) throw new Error('标记附件台账导入状态失败')
  return res.json()
}

// ─── 新员工培训（Server Actions）───

export async function generateNewEmployeeTrainingPlan(
  data: NewEmployeeTrainingPlanGenerateInput
): Promise<{ code: number; message: string; data: unknown }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/new-employee-training/plans/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    cache: 'no-store',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || err.detail || '生成培训计划失败')
  }
  revalidatePath('/hr/training/new-employee')
  return res.json()
}

export async function createManualNewEmployeeTrainingPlan(
  data: NewEmployeeTrainingManualAddInput
): Promise<{ code: number; message: string; data: unknown }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/new-employee-training/plans/manual-add`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    cache: 'no-store',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || err.detail || '手动新增新员工失败')
  }
  revalidatePath('/hr/training/new-employee')
  return res.json()
}

export async function updateNewEmployeeTrainingPlan(
  planId: string,
  data: NewEmployeeTrainingUpdateInput
): Promise<{ code: number; message: string; data: unknown }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/new-employee-training/plans/${planId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    cache: 'no-store',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || err.detail || '更新培训计划失败')
  }
  revalidatePath('/hr/training/new-employee')
  return res.json()
}

export async function addNewEmployeeTrainingItem(
  planId: string,
  data: NewEmployeeTrainingItemAddInput
): Promise<{ code: number; message: string; data: unknown }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/new-employee-training/plans/${planId}/items`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    cache: 'no-store',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || err.detail || '添加培训教材失败')
  }
  revalidatePath('/hr/training/new-employee')
  return res.json()
}

export async function startNewEmployeeTraining(
  planId: string,
  data: NewEmployeeTrainingStartInput
): Promise<{ code: number; message: string; data: unknown }> {
  const res = await authedFetch(
    `${API_BASE}/api/v1/hr/new-employee-training/plans/${planId}/start-training`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
      cache: 'no-store',
    }
  )
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || err.detail || '开始培训失败')
  }
  return res.json()
}

export async function deleteNewEmployeeTrainingPlan(
  planId: string
): Promise<{ code: number; message: string }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/new-employee-training/plans/${planId}`, {
    method: 'DELETE',
    cache: 'no-store',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || err.detail || '删除培训计划失败')
  }
  revalidatePath('/hr/training/new-employee')
  return res.json()
}

// ─── 新员工培训 - 添加参训人员 ───

export async function addNewEmployeeTrainingTrainees(
  planId: string,
  data: { item_ids: string[]; additional_trainees: { name: string; department: string }[] }
): Promise<{ code: number; message: string; data: unknown }> {
  const res = await authedFetch(
    `${API_BASE}/api/v1/hr/new-employee-training/plans/${planId}/start-training`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
      cache: 'no-store',
    }
  )
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || err.detail || '开始培训失败')
  }
  return res.json()
}

// ─── 岗位培训映射（Server Actions）───

export async function createPositionTrainingMappingAction(
  data: PositionTrainingMappingCreateInput
): Promise<{ code: number; message: string; data: unknown }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/position-training-mappings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    cache: 'no-store',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || err.detail || '创建岗位映射失败')
  }
  revalidatePath('/hr/training/new-employee')
  return res.json()
}

// ─── Email Actions ───

export async function sendOfferEmailAction(
  data: { candidate_id: string; to_email: string; subject: string; body: string }
): Promise<{ code: number; message: string; data?: unknown }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/email/send-offer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    cache: 'no-store',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || err.detail || '发送邮件失败')
  }
  return res.json()
}

export async function sendCandidateNoticeAction(
  candidateId: string,
  sceneCode: string
): Promise<{ code: number; message: string; data?: unknown }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/candidates/${candidateId}/send-notice`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scene_code: sceneCode }),
    cache: 'no-store',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || err.detail || '发送通知失败')
  }
  return res.json()
}

export async function browseFolderAction(): Promise<{ code: number; message: string; data?: { path?: string; error?: string } }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/email/browse-folder`, {
    method: 'POST',
    cache: 'no-store',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || err.detail || '打开文件夹对话框失败')
  }
  return res.json()
}

export async function uploadOfferTemplateAction(
  formData: FormData
): Promise<{ code: number; message: string; data?: unknown }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/email/upload-offer-template`, {
    method: 'POST',
    body: formData,
    cache: 'no-store',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || err.detail || '上传模板失败')
  }
  return res.json()
}

// ─── 合同审批结果 / 签署状态 Actions ───

export async function updateContractSignStatusAction(
  recordId: string,
  signedStatus: '已签署' | '拒签'
): Promise<{ code: number; message: string; data?: unknown }> {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/contracts/${recordId}/sign-status`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ signed_status: signedStatus }),
    cache: 'no-store',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || err.detail || '标记签署状态失败')
  }
  revalidatePath('/hr/contracts')
  return res.json()
}

// ─── 自定义培训部门 Actions ───

export async function addCustomTrainingDepartment(name: string) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/training/departments`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
    credentials: 'include',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || '添加部门失败')
  }
  const json = await res.json()
  return json.data as { name: string; id: string }
}

export async function deleteCustomTrainingDepartment(name: string) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/training/departments/${encodeURIComponent(name)}`, {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || '删除部门失败')
  }
  return true
}

// ─── Training Dept Mapping Actions ───

export interface TrainingDeptMappingCreateInput {
  source_name: string
  target_name?: string | null
  match_level: 'first' | 'second' | 'both'
  mapping_type: string
  priority?: number
  enabled?: boolean
  remark?: string | null
}

export interface TrainingDeptMappingUpdateInput {
  source_name?: string | null
  target_name?: string | null
  match_level?: 'first' | 'second' | 'both' | null
  mapping_type?: string | null
  priority?: number | null
  enabled?: boolean | null
  remark?: string | null
}

export async function createTrainingDeptMappingAction(data: TrainingDeptMappingCreateInput) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/training/dept-mappings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    credentials: 'include',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || '新增映射失败')
  }
  revalidatePath('/hr/settings/dept-mapping')
  return (await res.json()).data
}

export async function updateTrainingDeptMappingAction(id: string, data: TrainingDeptMappingUpdateInput) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/training/dept-mappings/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    credentials: 'include',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || '更新映射失败')
  }
  revalidatePath('/hr/settings/dept-mapping')
  return (await res.json()).data
}

export async function deleteTrainingDeptMappingAction(id: string) {
  const res = await authedFetch(`${API_BASE}/api/v1/hr/training/dept-mappings/${id}`, {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || '删除映射失败')
  }
  revalidatePath('/hr/settings/dept-mapping')
  return true
}
