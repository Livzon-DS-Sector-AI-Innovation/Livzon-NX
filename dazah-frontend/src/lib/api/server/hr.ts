/**
 * HR 模块 - 服务器端 API
 * 使用 API_BASE_URL 环境变量（Docker 内部网络）
 */

import { getAuthHeaders } from '@/lib/auth'

const API_BASE_URL = process.env.API_BASE_URL || 'http://localhost:8000'
const HR_TIMEOUT = 15000

/** 服务端读取 auth_token cookie，供请求后端时携带 Bearer 认证头 */
async function getAuthHeadersForServer(): Promise<Record<string, string> | undefined> {
  return getAuthHeaders()
}

interface ApiEnvelope<T> {
  code: number
  message: string
  data: T
  meta?: { total?: number; page?: number; page_size?: number }
}

async function serverApiFetch<T>(path: string, init?: RequestInit): Promise<ApiEnvelope<T>> {
  const ctrl = new AbortController()
  const tid = setTimeout(() => ctrl.abort(), HR_TIMEOUT)
  try {
    const res = await fetch(`${API_BASE_URL}${path}`, {
      cache: 'no-store',
      signal: ctrl.signal,
      ...init,
      headers: {
        ...(await getAuthHeadersForServer()),
        ...(init?.headers as Record<string, string> | undefined),
      },
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.message || err.detail || `HTTP ${res.status}`)
    }
    return (await res.json()) as ApiEnvelope<T>
  } finally {
    clearTimeout(tid)
  }
}

import type {
  Department,
  DepartureRecord,
  Employee,
  EmployeeStats,
  OnboardingRecord,
  PositionTransferRecord,
  AnnualTrainingPlan,
} from '@/types/hr'
import type { ContractVM } from '@/lib/api/client/hr'

export async function fetchPositionTransfersServer(params?: {
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
  return serverApiFetch<PositionTransferRecord[]>(
    `/api/v1/hr/position-transfers?${sp.toString()}`,
  )
}

// ─── 招聘/入职 服务端 GET（Server Component / Server Action 使用）───

export async function fetchJobPostingsServer(
  params?: { keyword?: string; page?: number; page_size?: number }
): Promise<{ code: number; message: string; data: Record<string, unknown>[]; meta?: Record<string, unknown> }> {
  const searchParams = new URLSearchParams()
  if (params?.keyword) searchParams.set('keyword', params.keyword)
  searchParams.set('page', String(params?.page || 1))
  searchParams.set('page_size', String(params?.page_size || 100))
  const res = await fetch(`${API_BASE_URL}/api/v1/hr/jobs?${searchParams.toString()}`, { cache: 'no-store', headers: await getAuthHeadersForServer() })
  if (!res.ok) throw new Error('获取职位列表失败')
  return res.json()
}

export async function fetchCandidatesServer(
  params?: { keyword?: string; fit_level?: string; interview_status?: string; page?: number; page_size?: number }
): Promise<{ code: number; message: string; data: Record<string, unknown>[]; meta?: Record<string, unknown> }> {
  const searchParams = new URLSearchParams()
  if (params?.keyword) searchParams.set('keyword', params.keyword)
  if (params?.fit_level) searchParams.set('fit_level', params.fit_level)
  if (params?.interview_status) searchParams.set('interview_status', params.interview_status)
  searchParams.set('page', String(params?.page || 1))
  searchParams.set('page_size', String(params?.page_size || 20))
  const res = await fetch(`${API_BASE_URL}/api/v1/hr/candidates?${searchParams.toString()}`, { cache: 'no-store', headers: await getAuthHeadersForServer() })
  if (!res.ok) throw new Error('获取候选人列表失败')
  return res.json()
}

export async function fetchOnboardingServer(
  params?: { keyword?: string; page?: number; page_size?: number }
): Promise<{ code: number; message: string; data: Record<string, unknown>[]; meta?: Record<string, unknown> }> {
  const searchParams = new URLSearchParams()
  if (params?.keyword) searchParams.set('keyword', params.keyword)
  searchParams.set('page', String(params?.page || 1))
  searchParams.set('page_size', String(params?.page_size || 20))
  const res = await fetch(`${API_BASE_URL}/api/v1/hr/onboarding?${searchParams.toString()}`, { cache: 'no-store', headers: await getAuthHeadersForServer() })
  if (!res.ok) throw new Error('获取入职列表失败')
  return res.json()
}

// ─── 迁移兼容的新厂台账（Server Component 使用）───

function buildNewFactoryQuery(params?: Record<string, string | number | undefined>) {
  const searchParams = new URLSearchParams()
  for (const [key, value] of Object.entries(params || {})) {
    if (value !== undefined && value !== '') searchParams.set(key, String(value))
  }
  return searchParams.toString()
}

export async function fetchNewEmployeesServer(params?: {
  department?: string
  status?: string
  keyword?: string
  page?: number
  page_size?: number
}) {
  const query = buildNewFactoryQuery({
    ...params,
    page: params?.page || 1,
    page_size: params?.page_size || 20,
  })
  return serverApiFetch<Employee[]>(`/api/v1/hr/new/employees?${query}`)
}

export async function fetchNewDepartmentsServer(params?: {
  keyword?: string
  page?: number
  page_size?: number
}) {
  const query = buildNewFactoryQuery({
    ...params,
    page: params?.page || 1,
    page_size: params?.page_size || 100,
  })
  return serverApiFetch<Department[]>(`/api/v1/hr/new/departments?${query}`)
}

export async function fetchNewOnboardingRecordsServer(params?: {
  department?: string
  position?: string
  keyword?: string
  page?: number
  page_size?: number
}) {
  const query = buildNewFactoryQuery({
    ...params,
    page: params?.page || 1,
    page_size: params?.page_size || 20,
  })
  return serverApiFetch<OnboardingRecord[]>(
    `/api/v1/hr/new/onboarding-records?${query}`,
  )
}

export async function fetchNewDepartureRecordsServer(params?: {
  department?: string
  offboarding_type?: string
  keyword?: string
  page?: number
  page_size?: number
}) {
  const query = buildNewFactoryQuery({
    ...params,
    page: params?.page || 1,
    page_size: params?.page_size || 20,
  })
  return serverApiFetch<DepartureRecord[]>(
    `/api/v1/hr/new/departure-records?${query}`,
  )
}

export async function fetchNewOffboardingRecordsServer(params?: {
  department?: string
  offboarding_type?: string
  keyword?: string
  page?: number
  page_size?: number
}) {
  const query = buildNewFactoryQuery({
    ...params,
    page: params?.page || 1,
    page_size: params?.page_size || 20,
  })
  return serverApiFetch<DepartureRecord[]>(
    `/api/v1/hr/new/offboarding-records?${query}`,
  )
}

// ─── 离职管理 服务端操作 ───

export async function generateOffboardingCertificateServer(recordId: string): Promise<ApiEnvelope<{ file_generated: boolean; employee_name: string }>> {
  return serverApiFetch(`/api/v1/hr/offboarding-records/${recordId}/certificate`, {
    method: 'POST',
  })
}

// ─── 员工统计 服务端 GET（员工管理仪表盘）───

export async function fetchEmployeeStatsServer(): Promise<ApiEnvelope<EmployeeStats>> {
  return serverApiFetch(`/api/v1/hr/employees/stats`)
}

// ─── 合同管理 服务端 GET ───

export async function fetchContractsServer(
  params?: { keyword?: string; contract_sequence?: string; page?: number; page_size?: number }
): Promise<{ code: number; message: string; data: { data: ContractVM[]; total: number; page: number; page_size: number }; meta?: Record<string, unknown> }> {
  const searchParams = new URLSearchParams()
  if (params?.keyword) searchParams.set('keyword', params.keyword)
  if (params?.contract_sequence) searchParams.set('contract_sequence', params.contract_sequence)
  searchParams.set('page', String(params?.page || 1))
  searchParams.set('page_size', String(params?.page_size || 20))
  const res = await fetch(`${API_BASE_URL}/api/v1/hr/contracts?${searchParams.toString()}`, { cache: 'no-store', headers: await getAuthHeadersForServer() })
  if (!res.ok) throw new Error('获取合同列表失败')
  return res.json()
}

// ─── 年度培训计划（Server Component 用）───

export async function fetchAnnualTrainingPlanByIdServer(
  id: string
): Promise<ApiEnvelope<AnnualTrainingPlan>> {
  return serverApiFetch(`/api/v1/hr/annual-training-plans/${id}`)
}

// ─── 合同审批结果（Server Component 用）───

import type { ContractApprovalResultVM } from '@/types/hr'

export async function fetchContractApprovalResultsServer(params?: {
  start_date?: string
  end_date?: string
  department?: string
  result?: 'approved' | 'rejected'
  page?: number
  page_size?: number
}): Promise<ApiEnvelope<ContractApprovalResultVM[]>> {
  const sp = new URLSearchParams()
  if (params?.start_date) sp.set('start_date', params.start_date)
  if (params?.end_date) sp.set('end_date', params.end_date)
  if (params?.department) sp.set('department', params.department)
  if (params?.result) sp.set('result', params.result)
  sp.set('page', String(params?.page || 1))
  sp.set('page_size', String(params?.page_size || 20))
  return serverApiFetch<ContractApprovalResultVM[]>(
    `/api/v1/hr/contracts/approval-results?${sp.toString()}`,
  )
}
