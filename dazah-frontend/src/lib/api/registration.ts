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
  return apiFetch(`/api/v1/registration/`)
}

// Authorization Letters
// Authorization Letters
export async function fetchAuthorizationLetters(params?: {
  page?: number
  page_size?: number
  product_name?: string
  preparation_unit?: string
}): Promise<{ data: AuthorizationLetter[]; meta: { total: number } }> {
  const searchParams = new URLSearchParams()
  if (params?.page) searchParams.set('page', String(params.page))
  if (params?.page_size) searchParams.set('page_size', String(params.page_size))
  if (params?.product_name) searchParams.set('product_name', params.product_name)
  const query = searchParams.toString()
  const res = await fetch(`/api/v1/registration/authorization-letters${query ? `?${query}` : ''}`)
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  const json = await res.json()
  return json
}

export async function getAuthorizationLetterDownloadUrl(id: string): Promise<string> {
  // The backend returns the authenticated file response directly; there is no
  // URL JSON envelope and no public object-storage URL to expose.
  return `/api/v1/registration/authorization-letters/${encodeURIComponent(id)}/download`
}

// Reference Standards
export async function fetchReferenceStandards(params?: {
  page?: number
  page_size?: number
  drug_name?: string
}): Promise<{ data: ReferenceStandardListItem[]; meta: { total: number } }> {
  const searchParams = new URLSearchParams()
  if (params?.page) searchParams.set('page', String(params.page))
  if (params?.page_size) searchParams.set('page_size', String(params.page_size))
  if (params?.drug_name) searchParams.set('drug_name', params.drug_name)
  const query = searchParams.toString()
  const res = await fetch(`/api/v1/registration/reference-standards${query ? `?${query}` : ''}`)
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  const json = await res.json()
  return json
}

export async function getReferenceStandardDownloadUrl(id: string): Promise<string> {
  return `/api/v1/registration/reference-standards/${encodeURIComponent(id)}/download`
}

export async function parseCOA(file: File): Promise<CoaParseResult> {
  const formData = new FormData()
  formData.append('file', file)
  const res = await fetch('/api/v1/registration/reference-standards/parse-coa', {
    method: 'POST',
    body: formData,
  })
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  const json = await res.json()
  return json.data
}

// Supplementary Replies
export async function fetchSupplementaryReplies(params?: {
  page?: number
  page_size?: number
  drug_name?: string
}): Promise<{ data: SupplementaryReplyListItem[]; meta: { total: number } }> {
  const searchParams = new URLSearchParams()
  if (params?.page) searchParams.set('page', String(params.page))
  if (params?.page_size) searchParams.set('page_size', String(params.page_size))
  if (params?.drug_name) searchParams.set('drug_name', params.drug_name)
  const query = searchParams.toString()
  const res = await fetch(`/api/v1/registration/supplementary-replies${query ? `?${query}` : ''}`)
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  const json = await res.json()
  return json
}

export async function getSupplementaryReplyDownloadUrl(id: string): Promise<string> {
  return `/api/v1/registration/supplementary-replies/${encodeURIComponent(id)}/download`
}
import type {
  AuthorizationLetter,
  ReferenceStandardListItem,
  SupplementaryReplyListItem,
} from '@/types/registration'

interface CoaParseResult {
  metadata: Record<string, string | null | undefined>
  raw_text?: string
}
