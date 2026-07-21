import {
  ResearchProject,
  ResearchProjectFilters,
  ResearchProjectListResponse,
  ResearchProjectCreate,
  ResearchProjectUpdate,
} from '@/types/rd'

async function apiFetch<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })
  if (!response.ok) {
    throw new Error(`请求失败: ${response.status} ${response.statusText}`)
  }
  const data = await response.json()
  return data.data
}

async function apiFetchPaginated(
  url: string,
  options?: RequestInit
): Promise<ResearchProjectListResponse> {
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })
  if (!response.ok) {
    throw new Error(`请求失败: ${response.status} ${response.statusText}`)
  }
  const result = await response.json()
  return {
    items: result.data || [],
    total: result.meta?.total || 0,
    page: result.meta?.page || 1,
    page_size: result.meta?.page_size || 20,
  }
}

export async function fetchResearchProjects(
  filters: ResearchProjectFilters = {}
): Promise<ResearchProjectListResponse> {
  const params = new URLSearchParams()
  if (filters.stage) params.set('stage', filters.stage)
  if (filters.status) params.set('status', filters.status)
  if (filters.keyword) params.set('keyword', filters.keyword)
  params.set('project_type', '')  // Only regular research projects
  params.set('page', String(filters.page || 1))
  params.set('page_size', String(filters.page_size || 20))
  return apiFetchPaginated(
    `/api/v1/research/projects?${params.toString()}`
  )
}

export async function fetchResearchProject(
  projectId: string
): Promise<ResearchProject> {
  return apiFetch(`/api/v1/research/projects/${projectId}`)
}

export async function createResearchProject(
  data: ResearchProjectCreate
): Promise<ResearchProject> {
  return apiFetch(`/api/v1/research/projects`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function updateResearchProject(
  projectId: string,
  data: ResearchProjectUpdate
): Promise<ResearchProject> {
  return apiFetch(`/api/v1/research/projects/${projectId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export async function deleteResearchProject(
  projectId: string
): Promise<void> {
  return apiFetch(`/api/v1/research/projects/${projectId}`, {
    method: 'DELETE',
  })
}

// ── EDBO+ 贝叶斯优化 ────────────────────────────────────────────────────

import { EDBOOptimizeResponse } from '@/types/rd'

export async function runEDBOOptimize(
  file: File,
  objectives: string[],
  objectiveModes: ('max' | 'min')[],
  batchSize: number,
  savePrediction: boolean = false
): Promise<EDBOOptimizeResponse> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('objectives', objectives.join(','))
  formData.append('objective_modes', objectiveModes.join(','))
  formData.append('batch_size', String(batchSize))
  formData.append('save_prediction', String(savePrediction))

  const response = await fetch(`/api/v1/research/edbo/optimize`, {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => null)
    const detail = errorData?.detail || errorData?.message || response.statusText
    throw new Error(`EDBO+ 优化失败: ${detail}`)
  }

  const result = await response.json()
  return result.data
}

export async function generateReactionScope(
  components: Record<string, (string | number)[]>,
  objectives: string[] = [],
  batchSize: number = 5
): Promise<{ 
    csv_data: string; 
    row_count: number; 
    columns: string[];
    recommended_experiments?: string;
    optimization_completed?: boolean;
    optimization_error?: string;
  }> {
  const response = await fetch(`/api/v1/research/edbo/generate-scope`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ components, objectives, batch_size: batchSize }),
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || '生成反应范围失败')
  }

  return response.json()
}
