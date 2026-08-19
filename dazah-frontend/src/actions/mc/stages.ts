'use server'
// MC 霉酚酸 — 提取 + 二次精制 + 混粉 + QC + 丁酯 Actions

import { revalidatePath } from 'next/cache'
import { getAuthHeaders } from '@/lib/auth'
import type { ApiResponse } from '@/types/production'

const API = process.env.API_BASE_URL || 'http://localhost:8000'
const BASE = '/api/v1/production/mc'
const REVALIDATE_PATH = '/production/batches/workshop/201-2'

async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<ApiResponse<T>> {
  const authHeaders = await getAuthHeaders()
  const { headers: optHeaders, ...rest } = options || {}
  const r = await fetch(`${API}${endpoint}`, { headers: { ...authHeaders, ...optHeaders }, ...rest })
  return r.json()
}

function qs(params: Record<string, any>) { const sp = new URLSearchParams(); Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '') sp.set(k, String(v)) }); return sp.size ? '?' + sp.toString() : '' }

// ═══════════ 提取 ═══════════
export async function getExtractionRecords(params: Record<string, any> = {}) { return fetchApi<any[]>(`${BASE}/extraction-records${qs(params)}`) }
export async function createExtractionRecord(data: any) { const res = await fetchApi<any>(`${BASE}/extraction-records`, { method: 'POST', body: JSON.stringify(data) }); revalidatePath(REVALIDATE_PATH); return res }
export async function updateExtractionRecord(id: string, data: any) { return fetchApi<any>(`${BASE}/extraction-records/${id}`, { method: 'PUT', body: JSON.stringify(data) }) }
export async function deleteExtractionRecord(id: string) { return fetchApi<null>(`${BASE}/extraction-records/${id}`, { method: 'DELETE' }) }

export async function getExtractionInputs(batchNo: string) { return fetchApi<any[]>(`${BASE}/extraction-records/${batchNo}/inputs`) }
export async function createExtractionInput(data: any) { return fetchApi<any>(`${BASE}/extraction-inputs`, { method: 'POST', body: JSON.stringify(data) }) }
export async function updateExtractionInput(id: string, data: any) { return fetchApi<any>(`${BASE}/extraction-inputs/${id}`, { method: 'PUT', body: JSON.stringify(data) }) }
export async function deleteExtractionInput(id: string) { return fetchApi<null>(`${BASE}/extraction-inputs/${id}`, { method: 'DELETE' }) }

// ═══════════ 二次精制 ═══════════
export async function getRefinementRecords(params: Record<string, any> = {}) { return fetchApi<any[]>(`${BASE}/refinement-records${qs(params)}`) }
export async function createRefinementRecord(data: any) { const res = await fetchApi<any>(`${BASE}/refinement-records`, { method: 'POST', body: JSON.stringify(data) }); revalidatePath(REVALIDATE_PATH); return res }
export async function updateRefinementRecord(id: string, data: any) { return fetchApi<any>(`${BASE}/refinement-records/${id}`, { method: 'PUT', body: JSON.stringify(data) }) }
export async function deleteRefinementRecord(id: string) { return fetchApi<null>(`${BASE}/refinement-records/${id}`, { method: 'DELETE' }) }

export async function getRefinementInputs(batchNo: string) { return fetchApi<any[]>(`${BASE}/refinement-records/${batchNo}/inputs`) }
export async function createRefinementInput(data: any) { return fetchApi<any>(`${BASE}/refinement-inputs`, { method: 'POST', body: JSON.stringify(data) }) }
export async function updateRefinementInput(id: string, data: any) { return fetchApi<any>(`${BASE}/refinement-inputs/${id}`, { method: 'PUT', body: JSON.stringify(data) }) }
export async function deleteRefinementInput(id: string) { return fetchApi<null>(`${BASE}/refinement-inputs/${id}`, { method: 'DELETE' }) }

// ═══════════ 混粉 ═══════════
export async function getBlendingRecords(params: Record<string, any> = {}) { return fetchApi<any[]>(`${BASE}/blending-records${qs(params)}`) }
export async function createBlendingRecord(data: any) { const res = await fetchApi<any>(`${BASE}/blending-records`, { method: 'POST', body: JSON.stringify(data) }); revalidatePath(REVALIDATE_PATH); return res }
export async function updateBlendingRecord(id: string, data: any) { return fetchApi<any>(`${BASE}/blending-records/${id}`, { method: 'PUT', body: JSON.stringify(data) }) }
export async function deleteBlendingRecord(id: string) { return fetchApi<null>(`${BASE}/blending-records/${id}`, { method: 'DELETE' }) }

export async function getBlendingInputs(batchNo: string) { return fetchApi<any[]>(`${BASE}/blending-records/${batchNo}/inputs`) }
export async function createBlendingInput(data: any) { return fetchApi<any>(`${BASE}/blending-inputs`, { method: 'POST', body: JSON.stringify(data) }) }
export async function deleteBlendingInput(id: string) { return fetchApi<null>(`${BASE}/blending-inputs/${id}`, { method: 'DELETE' }) }

export async function calculateBlendImpurities(batchNo: string) { return fetchApi<any>(`${BASE}/blending-records/${batchNo}/calculate`, { method: 'POST' }) }

// ═══════════ QC检验 ═══════════
export async function getQcInspections(params: Record<string, any> = {}) { return fetchApi<any[]>(`${BASE}/qc-inspections${qs(params)}`) }
export async function createQcInspection(data: any) { return fetchApi<any>(`${BASE}/qc-inspections`, { method: 'POST', body: JSON.stringify(data) }) }
export async function updateQcInspection(id: string, data: any) { return fetchApi<any>(`${BASE}/qc-inspections/${id}`, { method: 'PUT', body: JSON.stringify(data) }) }

export async function getQcInspectionItems(qcId: string) { return fetchApi<any[]>(`${BASE}/qc-inspections/${qcId}/items`) }
export async function createQcInspectionItem(data: any) { return fetchApi<any>(`${BASE}/qc-inspection-items`, { method: 'POST', body: JSON.stringify(data) }) }

// ═══════════ 乙酸丁酯 — 已迁移至 butyl_acetate_records 表 ═══════════
// 旧 API (ba-inventory/ba-consumption/ba-checks) 已删除，统一使用 ba-records
