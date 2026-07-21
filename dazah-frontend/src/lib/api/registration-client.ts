'use client'

export interface DrugNode {
  id: string
  drug_id: string
  node_index: number
  actual_date: string | null
  created_at: string
  updated_at: string
}

export interface Drug {
  id: string
  name: string
  type: '仿制药' | '创新药' | '原料药'
  acceptance_date: string
  current_node: number
  created_at: string
  updated_at: string
  nodes: DrugNode[]
}

export interface DrugCreate {
  name: string
  type: '仿制药' | '创新药' | '原料药'
  acceptance_date: string
}

export interface DrugUpdate {
  name?: string
  type?: '仿制药' | '创新药' | '原料药'
  acceptance_date?: string
  nodes?: { node_index: number; actual_date: string | null }[]
}

export interface Holiday {
  id: string
  year: number
  date: string
  type: 'holiday' | 'makeup'
  description: string | null
  created_at: string
  updated_at: string
}

export interface ReviewNodeConfig {
  index: number
  name: string
  days: number
}

export interface ApiData<T> {
  data: T
  message: string
  success: boolean
}

const headers = { 'Content-Type': 'application/json' }

// ====== 药品 ======
export async function fetchDrugs(): Promise<Drug[]> {
  const res = await fetch(`/api/v1/registration/drugs/`)
  const json: ApiData<Drug[]> = await res.json()
  return json.data || []
}

export async function fetchDrug(id: string): Promise<Drug> {
  const res = await fetch(`/api/v1/registration/drugs/${id}`)
  const json: ApiData<Drug> = await res.json()
  return json.data
}

export async function createDrug(data: DrugCreate): Promise<Drug> {
  const res = await fetch(`/api/v1/registration/drugs/`, {
    method: 'POST',
    headers,
    body: JSON.stringify(data),
  })
  const json: ApiData<Drug> = await res.json()
  return json.data
}

export async function updateDrug(id: string, data: DrugUpdate): Promise<Drug> {
  const res = await fetch(`/api/v1/registration/drugs/${id}`, {
    method: 'PUT',
    headers,
    body: JSON.stringify(data),
  })
  const json: ApiData<Drug> = await res.json()
  return json.data
}

export async function deleteDrug(id: string): Promise<void> {
  await fetch(`/api/v1/registration/drugs/${id}`, { method: 'DELETE' })
}

// ====== 审评节点配置 ======
export async function fetchReviewNodes(): Promise<ReviewNodeConfig[]> {
  const res = await fetch(`/api/v1/registration/drugs/nodes`)
  const json: ApiData<ReviewNodeConfig[]> = await res.json()
  return json.data || []
}

// ====== 节假日 ======
export async function fetchHolidays(year?: number): Promise<Holiday[]> {
  const url = year
    ? `/api/v1/registration/holidays/?year=${year}`
    : `/api/v1/registration/holidays/`
  const res = await fetch(url)
  const json: ApiData<Holiday[]> = await res.json()
  return json.data || []
}
