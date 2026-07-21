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
  return data.data ?? data
}

export async function fetchModuleInfo(): Promise<{ code: string; name: string; description: string }> {
  return apiFetch(`/api/v1/research/`)
}

export async function fetchOptimizations(params?: {
  page?: number
  page_size?: number
  status?: string
  keyword?: string
}): Promise<{ items: any[]; total: number; page: number; page_size: number }> {
  const searchParams = new URLSearchParams()
  if (params?.page) searchParams.set('page', String(params.page))
  if (params?.page_size) searchParams.set('page_size', String(params.page_size))
  if (params?.status) searchParams.set('status', params.status)
  if (params?.keyword) searchParams.set('keyword', params.keyword)
  const query = searchParams.toString()
  const response = await fetch(`/api/v1/research/optimizations${query ? `?${query}` : ''}`)
  if (!response.ok) {
    throw new Error(`请求失败: ${response.status} ${response.statusText}`)
  }
  const json = await response.json()
  return {
    items: json.data ?? [],
    total: json.meta?.total ?? 0,
    page: json.meta?.page ?? 1,
    page_size: json.meta?.page_size ?? 20,
  }
}

export async function createOptimization(data: {
  name: string
  project_id?: string
  source_route_id?: string
  source_route_name?: string
  description?: string
}): Promise<{ id: string; optimization_no: string; name: string; status: string; current_module: string }> {
  return apiFetch('/api/v1/research/optimizations', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function deleteOptimization(id: string): Promise<{ message: string }> {
  return apiFetch(`/api/v1/research/optimizations/${id}`, {
    method: 'DELETE',
  })
}

export async function updateOptimization(id: string, data: {
  name?: string
  status?: string
  current_module?: string
  description?: string
}): Promise<{ id: string; optimization_no: string; name: string; status: string; current_module: string }> {
  return apiFetch(`/api/v1/research/optimizations/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export async function createRoute(data: {
  name: string
  project_id?: string
  source?: string
  source_reference?: string
  description?: string
}): Promise<{ id: string; route_no: string }> {
  return apiFetch('/api/v1/research/routes', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function updateRoute(id: string, data: any): Promise<{ id: string; message: string }> {
  return apiFetch(`/api/v1/research/routes/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export async function deleteRoute(id: string): Promise<{ message: string }> {
  return apiFetch(`/api/v1/research/routes/${id}`, {
    method: 'DELETE',
  })
}

export async function fetchRoutes(params?: {
  page?: number
  page_size?: number
  status?: string
  keyword?: string
}): Promise<{ items: any[]; total: number }> {
  const searchParams = new URLSearchParams()
  if (params?.page) searchParams.set('page', String(params.page))
  if (params?.page_size) searchParams.set('page_size', String(params.page_size))
  if (params?.status) searchParams.set('status', params.status)
  if (params?.keyword) searchParams.set('keyword', params.keyword)
  const query = searchParams.toString()
  const res = await fetch(`/api/v1/research/routes${query ? `?${query}` : ''}`)
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  const json = await res.json()
  return { items: json.data, total: json.meta?.total || 0 }
}

export async function fetchRouteById(routeId: string): Promise<any> {
  const res = await fetch(`/api/v1/research/routes/${routeId}`)
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  const json = await res.json()
  return json.data
}
