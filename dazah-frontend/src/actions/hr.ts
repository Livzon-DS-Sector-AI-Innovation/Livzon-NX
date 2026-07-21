'use server'

import { getServerApiBaseUrl } from '@/lib/server-api'
import { revalidatePath } from 'next/cache'
import {
  EmployeeCreateInput,
  EmployeeUpdateInput,
  EmployeeListResponse,
  DepartmentCreateInput,
  DepartmentUpdateInput,
  DepartmentListResponse,
  TeamCreateInput,
  TeamUpdateInput,
  TeamListResponse,
  OffboardingRecordCreateInput,
  OffboardingRecordUpdateInput,
  OffboardingRecordListResponse,
} from '@/types/hr'

const API_BASE = getServerApiBaseUrl()

export async function fetchEmployeesAction(
  params?: {
    department?: string
    status?: string
    keyword?: string
    page?: number
    page_size?: number
  }
): Promise<EmployeeListResponse> {
  const searchParams = new URLSearchParams()
  if (params?.department) searchParams.set('department', params.department)
  if (params?.status) searchParams.set('status', params.status)
  if (params?.keyword) searchParams.set('keyword', params.keyword)
  searchParams.set('page', String(params?.page || 1))
  searchParams.set('page_size', String(params?.page_size || 20))

  const res = await fetch(`${API_BASE}/api/v1/hr/employees?${searchParams.toString()}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取员工列表失败')
  return res.json()
}

export async function createEmployee(data: EmployeeCreateInput) {
  const res = await fetch(`${API_BASE}/api/v1/hr/employees`, {
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
  const res = await fetch(`${API_BASE}/api/v1/hr/employees/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || '更新员工失败')
  }
  revalidatePath('/hr/profile')
  return res.json()
}

export async function deleteEmployee(id: string) {
  const res = await fetch(`${API_BASE}/api/v1/hr/employees/${id}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || '删除员工失败')
  }
  revalidatePath('/hr/profile')
  return res.json()
}

// ─── Feishu Sync Actions ───

export async function syncFromFeishuAction() {
  const res = await fetch(`${API_BASE}/api/v1/hr/employees/sync-from-feishu`, {
    method: 'POST',
    cache: 'no-store',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || '从飞书同步失败')
  }
  revalidatePath('/hr/profile')
  return res.json()
}

export async function syncToFeishuAction(id: string) {
  const res = await fetch(`${API_BASE}/api/v1/hr/employees/${id}/sync-to-feishu`, {
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
    page?: number
    page_size?: number
  }
): Promise<DepartmentListResponse> {
  const searchParams = new URLSearchParams()
  if (params?.keyword) searchParams.set('keyword', params.keyword)
  searchParams.set('page', String(params?.page || 1))
  searchParams.set('page_size', String(params?.page_size || 100))

  const res = await fetch(`${API_BASE}/api/v1/hr/departments?${searchParams.toString()}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取部门列表失败')
  return res.json()
}

export async function createDepartment(data: DepartmentCreateInput) {
  const res = await fetch(`${API_BASE}/api/v1/hr/departments`, {
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
  const res = await fetch(`${API_BASE}/api/v1/hr/departments/${id}`, {
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
  const res = await fetch(`${API_BASE}/api/v1/hr/departments/${id}`, {
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

  const res = await fetch(`${API_BASE}/api/v1/hr/teams?${searchParams.toString()}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取班组列表失败')
  return res.json()
}

export async function createTeam(data: TeamCreateInput) {
  const res = await fetch(`${API_BASE}/api/v1/hr/teams`, {
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
  const res = await fetch(`${API_BASE}/api/v1/hr/teams/${id}`, {
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
  const res = await fetch(`${API_BASE}/api/v1/hr/teams/${id}`, {
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

  const res = await fetch(`${API_BASE}/api/v1/hr/offboarding-records?${searchParams.toString()}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取离职记录失败')
  return res.json()
}

export async function createOffboardingRecord(data: OffboardingRecordCreateInput) {
  const res = await fetch(`${API_BASE}/api/v1/hr/offboarding-records`, {
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
  const res = await fetch(`${API_BASE}/api/v1/hr/offboarding-records/${id}`, {
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
  const res = await fetch(`${API_BASE}/api/v1/hr/offboarding-records/${id}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.message || '删除离职记录失败')
  }
  revalidatePath('/hr/offboarding')
  return res.json()
}

// ─── STUB: Annual Training Plan Actions (not yet implemented) ───

export async function createAnnualTrainingPlan(data: { year: number; department: string; status: string }) {
  throw new Error('createAnnualTrainingPlan: 功能尚未实现')
  return { data: { id: '' } }
}

export async function deleteAnnualTrainingPlan(id: string) {
  throw new Error('deleteAnnualTrainingPlan: 功能尚未实现')
  return { success: true, message: "功能尚未实现" }
}

export async function batchUpdatePlanItems(planId: string, data: { items: any[] }) {
  throw new Error('batchUpdatePlanItems: 功能尚未实现')
  return { success: true, message: "功能尚未实现" }
}

// ─── STUB: Candidate/Recruitment Actions (not yet implemented) ───

export async function createCandidateAction(formData: FormData) {
  throw new Error('createCandidateAction: 功能尚未实现')
  return { success: true, message: "功能尚未实现" }
}

export async function parseResumePreviewAction(formData: FormData) {
  throw new Error('parseResumePreviewAction: 功能尚未实现')
  return { data: { gender: "", school: "", education: "", major: "", match_report: "", recommendation_level: "" } }
}

export async function syncCandidateToFeishuAction(candidateId: string) {
  throw new Error('syncCandidateToFeishuAction: 功能尚未实现')
  return { success: true, message: "功能尚未实现" }
}

export async function updateCandidateAction(candidateId: string, data: any) {
  throw new Error('updateCandidateAction: 功能尚未实现')
  return { success: true, message: "功能尚未实现" }
}

export async function updateCandidateRecommendationLevelAction(candidateId: string, level: string) {
  throw new Error('updateCandidateRecommendationLevelAction: 功能尚未实现')
  return { success: true, message: "功能尚未实现" }
}

export async function syncCandidatesFromFeishuAction() {
  throw new Error('syncCandidatesFromFeishuAction: 功能尚未实现')
  return { success: true, message: "功能尚未实现" }
}

export async function deleteCandidateAction(candidateId: string) {
  throw new Error('deleteCandidateAction: 功能尚未实现')
  return { success: true, message: "功能尚未实现" }
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

export async function fetchTeams(
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

  const res = await fetch(`${API_BASE}/api/v1/hr/teams?${searchParams.toString()}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取班组列表失败')
  return res.json()
}

export async function fetchOnboardingRecords(
  params?: {
    employee_id?: string
    department?: string
    position?: string
    is_employed?: string
    keyword?: string
    page?: number
    page_size?: number
  }
): Promise<any> {
  const searchParams = new URLSearchParams()
  if (params?.employee_id) searchParams.set('employee_id', params.employee_id)
  if (params?.department) searchParams.set('department', params.department)
  if (params?.position) searchParams.set('position', params.position)
  if (params?.is_employed) searchParams.set('is_employed', params.is_employed)
  if (params?.keyword) searchParams.set('keyword', params.keyword)
  searchParams.set('page', String(params?.page || 1))
  searchParams.set('page_size', String(params?.page_size || 20))

  const res = await fetch(`${API_BASE}/api/v1/hr/onboarding-records?${searchParams.toString()}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取入职记录失败')
  return res.json()
}

export async function fetchDepartureRecords(
  params?: {
    department?: string
    offboarding_type?: string
    keyword?: string
    page?: number
    page_size?: number
  }
): Promise<any> {
  const searchParams = new URLSearchParams()
  if (params?.department) searchParams.set('department', params.department)
  if (params?.offboarding_type) searchParams.set('offboarding_type', params.offboarding_type)
  if (params?.keyword) searchParams.set('keyword', params.keyword)
  searchParams.set('page', String(params?.page || 1))
  searchParams.set('page_size', String(params?.page_size || 20))

  const res = await fetch(`${API_BASE}/api/v1/hr/departure-records?${searchParams.toString()}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取离职台账失败')
  return res.json()
}

export async function fetchEmployeeById(id: string): Promise<any> {
  const res = await fetch(`${API_BASE}/api/v1/hr/employees/${id}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取员工详情失败')
  return res.json()
}

export async function fetchCandidateById(id: string): Promise<any> {
  const res = await fetch(`${API_BASE}/api/v1/hr/candidates/${id}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取候选人详情失败')
  return res.json()
}

export async function fetchCandidates(params: any = {}): Promise<any> {
  const searchParams = new URLSearchParams()
  if (params.keyword) searchParams.set('keyword', params.keyword)
  if (params.status) searchParams.set('status', params.status)
  searchParams.set('page', String(params.page || 1))
  searchParams.set('page_size', String(params.page_size || 20))

  const res = await fetch(`${API_BASE}/api/v1/hr/candidates?${searchParams.toString()}`, {
    cache: 'no-store',
  })
  if (!res.ok) return { data: [], meta: { total: 0 } }
  return res.json()
}

export async function fetchNewEmployees(params: any = {}): Promise<EmployeeListResponse> {
  const searchParams = new URLSearchParams()
  if (params.department) searchParams.set('department', params.department)
  if (params.status) searchParams.set('status', params.status)
  if (params.keyword) searchParams.set('keyword', params.keyword)
  searchParams.set('page', String(params.page || 1))
  searchParams.set('page_size', String(params.page_size || 20))

  const res = await fetch(`${API_BASE}/api/v1/hr/new/employees?${searchParams.toString()}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取新厂员工列表失败')
  return res.json()
}

export async function fetchNewDepartments(params: any = {}): Promise<DepartmentListResponse> {
  const searchParams = new URLSearchParams()
  if (params.keyword) searchParams.set('keyword', params.keyword)
  searchParams.set('page', String(params.page || 1))
  searchParams.set('page_size', String(params.page_size || 100))

  const res = await fetch(`${API_BASE}/api/v1/hr/new/departments?${searchParams.toString()}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取新厂部门列表失败')
  return res.json()
}

export async function fetchNewOnboardingRecords(params: any = {}): Promise<any> {
  const searchParams = new URLSearchParams()
  if (params.department) searchParams.set('department', params.department)
  if (params.position) searchParams.set('position', params.position)
  if (params.keyword) searchParams.set('keyword', params.keyword)
  searchParams.set('page', String(params.page || 1))
  searchParams.set('page_size', String(params.page_size || 20))

  const res = await fetch(`${API_BASE}/api/v1/hr/new/onboarding-records?${searchParams.toString()}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取新厂入职台账失败')
  return res.json()
}

export async function fetchNewDepartureRecords(params: any = {}): Promise<any> {
  const searchParams = new URLSearchParams()
  if (params.department) searchParams.set('department', params.department)
  if (params.offboarding_type) searchParams.set('offboarding_type', params.offboarding_type)
  if (params.keyword) searchParams.set('keyword', params.keyword)
  searchParams.set('page', String(params.page || 1))
  searchParams.set('page_size', String(params.page_size || 20))

  const res = await fetch(`${API_BASE}/api/v1/hr/new/departure-records?${searchParams.toString()}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取新厂离职台账失败')
  return res.json()
}

export async function fetchNewOffboardingRecords(params: any = {}): Promise<any> {
  const searchParams = new URLSearchParams()
  if (params.department) searchParams.set('department', params.department)
  if (params.offboarding_type) searchParams.set('offboarding_type', params.offboarding_type)
  if (params.keyword) searchParams.set('keyword', params.keyword)
  searchParams.set('page', String(params.page || 1))
  searchParams.set('page_size', String(params.page_size || 20))

  const res = await fetch(`${API_BASE}/api/v1/hr/new/offboarding-records?${searchParams.toString()}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取新厂离职管理失败')
  return res.json()
}

export async function fetchAnnualTrainingPlanById(id: string): Promise<any> {
  const res = await fetch(`${API_BASE}/api/v1/hr/annual-training-plans/${id}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取年度培训计划详情失败')
  return res.json()
}

export async function fetchPlanItems(id: string): Promise<any> {
  const res = await fetch(`${API_BASE}/api/v1/hr/annual-training-plans/${id}/items`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取年度计划明细失败')
  return res.json()
}

export async function fetchTrainingRecords(params: any = {}): Promise<any> {
  const searchParams = new URLSearchParams()
  if (params.employee_id) searchParams.set('employee_id', params.employee_id)
  if (params.training_type) searchParams.set('training_type', params.training_type)
  if (params.keyword) searchParams.set('keyword', params.keyword)
  searchParams.set('page', String(params.page || 1))
  searchParams.set('page_size', String(params.page_size || 20))

  const res = await fetch(`${API_BASE}/api/v1/hr/training-records?${searchParams.toString()}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取培训记录失败')
  return res.json()
}

export async function fetchTrainingPlans(params: any = {}): Promise<any> {
  const searchParams = new URLSearchParams()
  if (params.year) searchParams.set('year', params.year)
  if (params.department) searchParams.set('department', params.department)
  searchParams.set('page', String(params.page || 1))
  searchParams.set('page_size', String(params.page_size || 20))

  const res = await fetch(`${API_BASE}/api/v1/hr/training-plans?${searchParams.toString()}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取培训计划失败')
  return res.json()
}

export async function fetchEmployeeByNumber(employeeNumber: string): Promise<any> {
  const res = await fetch(`${API_BASE}/api/v1/hr/employees/by-number/${employeeNumber}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取员工详情失败')
  return res.json()
}
