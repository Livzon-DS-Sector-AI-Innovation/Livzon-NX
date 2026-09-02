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
