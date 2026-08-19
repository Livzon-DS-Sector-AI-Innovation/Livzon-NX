'use server'

import { revalidatePath } from 'next/cache'
import { getAuthHeaders } from '@/lib/auth'
import type {
  Batch,
  BatchMaterial,
  ProductionPlan,
  ProcessSpec,
  ProcessStep,
  ProcessParameter,
  ProductionRecord,
  MaterialBalance,
  FermentationRecord,
  BatchFormData,
  BatchMaterialFormData,
  ProductionPlanFormData,
  ProcessSpecFormData,
  ProcessStepFormData,
  ProcessParameterFormData,
  ProductionRecordFormData,
  FermentationFormData,
  FermentationQueryParams,
  BatchQueryParams,
  PlanQueryParams,
  ProcessSpecQueryParams,
  ApiResponse,
} from '@/types/production'

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'

// ============ Helper Functions ============

async function fetchApi<T>(
  endpoint: string,
  options?: RequestInit
): Promise<ApiResponse<T>> {
  const authHeaders = await getAuthHeaders()
  const { headers: optHeaders, ...restOptions } = options || {}
  const response = await fetch(`${API_BASE}${endpoint}`, {
    headers: {
      ...authHeaders,
      ...optHeaders,
    },
    ...restOptions,
  })
  return response.json()
}

// ============ Batch Actions ============

export async function getBatches(params: BatchQueryParams = {}) {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) searchParams.set('page_size', String(params.page_size))
  if (params.status) searchParams.set('status', params.status)
  if (params.product_code) searchParams.set('product_code', params.product_code)
  if (params.batch_no) searchParams.set('batch_no', params.batch_no)

  const queryString = searchParams.toString()
  const endpoint = `/api/v1/production/batches${queryString ? `?${queryString}` : ''}`
  return fetchApi<Batch[]>(endpoint)
}

export async function getBatch(id: string) {
  return fetchApi<Batch>(`/api/v1/production/batches/${id}`)
}

export async function createBatch(data: BatchFormData) {
  const response = await fetchApi<Batch>('/api/v1/production/batches', {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/production/batches')
  return response
}

export async function updateBatch(id: string, data: Partial<BatchFormData>) {
  const response = await fetchApi<Batch>(`/api/v1/production/batches/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath('/production/batches')
  return response
}

export async function updateBatchStatus(id: string, status: string) {
  const response = await fetchApi<Batch>(`/api/v1/production/batches/${id}/status`, {
    method: 'PUT',
    body: JSON.stringify({ status }),
  })
  revalidatePath('/production/batches')
  return response
}

export async function deleteBatch(id: string) {
  const response = await fetchApi<null>(`/api/v1/production/batches/${id}`, {
    method: 'DELETE',
  })
  revalidatePath('/production/batches')
  return response
}

// ============ Batch Material Actions ============

export async function getBatchMaterials(batchId: string) {
  return fetchApi<BatchMaterial[]>(`/api/v1/production/batches/${batchId}/materials`)
}

export async function addBatchMaterial(batchId: string, data: BatchMaterialFormData) {
  const response = await fetchApi<BatchMaterial>(`/api/v1/production/batches/${batchId}/materials`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath(`/production/batches/${batchId}`)
  return response
}

export async function updateBatchMaterial(id: string, data: Partial<BatchMaterialFormData>) {
  return fetchApi<BatchMaterial>(`/api/v1/production/materials/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export async function deleteBatchMaterial(id: string) {
  return fetchApi<null>(`/api/v1/production/materials/${id}`, {
    method: 'DELETE',
  })
}

// ============ Production Plan Actions ============

export async function getPlans(params: PlanQueryParams = {}) {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) searchParams.set('page_size', String(params.page_size))
  if (params.product_name) searchParams.set('product_name', params.product_name)
  if (params.workshop) searchParams.set('workshop', params.workshop)

  const queryString = searchParams.toString()
  const endpoint = `/api/v1/production/plans${queryString ? `?${queryString}` : ''}`
  return fetchApi<ProductionPlan[]>(endpoint)
}

export async function getPlan(id: string) {
  return fetchApi<ProductionPlan>(`/api/v1/production/plans/${id}`)
}

export async function createPlan(data: ProductionPlanFormData) {
  const response = await fetchApi<ProductionPlan>('/api/v1/production/plans', {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/production/plan')
  return response
}

export async function updatePlan(id: string, data: Partial<ProductionPlanFormData>) {
  const response = await fetchApi<ProductionPlan>(`/api/v1/production/plans/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath('/production/plan')
  return response
}

export async function deletePlan(id: string) {
  const response = await fetchApi<null>(`/api/v1/production/plans/${id}`, {
    method: 'DELETE',
  })
  revalidatePath('/production/plan')
  return response
}

// ============ Process Spec Actions ============

export async function getProcessSpecs(params: ProcessSpecQueryParams = {}) {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) searchParams.set('page_size', String(params.page_size))
  if (params.status) searchParams.set('status', params.status)
  if (params.product_code) searchParams.set('product_code', params.product_code)

  const queryString = searchParams.toString()
  const endpoint = `/api/v1/production/process-specs${queryString ? `?${queryString}` : ''}`
  return fetchApi<ProcessSpec[]>(endpoint)
}

export async function getProcessSpec(id: string) {
  return fetchApi<ProcessSpec>(`/api/v1/production/process-specs/${id}`)
}

export async function createProcessSpec(data: ProcessSpecFormData) {
  const response = await fetchApi<ProcessSpec>('/api/v1/production/process-specs', {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/production/process')
  return response
}

export async function updateProcessSpec(id: string, data: Partial<ProcessSpecFormData>) {
  const response = await fetchApi<ProcessSpec>(`/api/v1/production/process-specs/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath('/production/process')
  return response
}

export async function deleteProcessSpec(id: string) {
  const response = await fetchApi<null>(`/api/v1/production/process-specs/${id}`, {
    method: 'DELETE',
  })
  revalidatePath('/production/process')
  return response
}

// ============ Process Step Actions ============

export async function getProcessSteps(specId: string) {
  return fetchApi<ProcessStep[]>(`/api/v1/production/process-specs/${specId}/steps`)
}

export async function createProcessStep(data: ProcessStepFormData & { spec_id: string }) {
  const response = await fetchApi<ProcessStep>('/api/v1/production/steps', {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath(`/production/process/${data.spec_id}`)
  return response
}

export async function updateProcessStep(id: string, data: Partial<ProcessStepFormData>) {
  return fetchApi<ProcessStep>(`/api/v1/production/steps/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export async function deleteProcessStep(id: string) {
  return fetchApi<null>(`/api/v1/production/steps/${id}`, {
    method: 'DELETE',
  })
}

// ============ Process Parameter Actions ============

export async function getProcessParameters(stepId: string) {
  return fetchApi<ProcessParameter[]>(`/api/v1/production/steps/${stepId}/parameters`)
}

export async function createProcessParameter(data: ProcessParameterFormData & { step_id: string }) {
  const response = await fetchApi<ProcessParameter>('/api/v1/production/parameters', {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath(`/production/process`)
  return response
}

export async function updateProcessParameter(id: string, data: ProcessParameterFormData) {
  const response = await fetchApi<ProcessParameter>(`/api/v1/production/parameters/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath(`/production/process`)
  return response
}

export async function deleteProcessParameter(id: string) {
  return fetchApi<null>(`/api/v1/production/parameters/${id}`, {
    method: 'DELETE',
  })
}

// ============ Production Record Actions ============

export async function getProductionRecords(batchId: string, page = 1, pageSize = 100) {
  return fetchApi<ProductionRecord[]>(
    `/api/v1/production/batches/${batchId}/records?page=${page}&page_size=${pageSize}`
  )
}

export async function createProductionRecord(data: ProductionRecordFormData & { batch_id: string }) {
  const response = await fetchApi<ProductionRecord>('/api/v1/production/records', {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath(`/production/records`)
  return response
}

export async function updateProductionRecord(id: string, data: Partial<ProductionRecordFormData>) {
  return fetchApi<ProductionRecord>(`/api/v1/production/records/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export async function deleteProductionRecord(id: string) {
  return fetchApi<null>(`/api/v1/production/records/${id}`, {
    method: 'DELETE',
  })
}

// ============ Material Balance Actions ============

export async function getMaterialBalance(batchId: string) {
  return fetchApi<MaterialBalance>(`/api/v1/production/batches/${batchId}/balance`)
}

export async function calculateMaterialBalance(batchId: string, minBalanceRate = 95.0) {
  const response = await fetchApi<MaterialBalance>(
    `/api/v1/production/batches/${batchId}/balance/calculate?min_balance_rate=${minBalanceRate}`,
    { method: 'POST' }
  )
  revalidatePath(`/production/balance`)
  return response
}

// ============ Fermentation Record Actions ============

export async function getFermentationRecords(params: FermentationQueryParams = {}) {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) searchParams.set('page_size', String(params.page_size))
  if (params.product_name) searchParams.set('product_name', params.product_name)
  if (params.batch_no) searchParams.set('batch_no', params.batch_no)
  if (params.status) searchParams.set('status', params.status)
  if (params.fermenter) searchParams.set('fermenter', params.fermenter)

  const queryString = searchParams.toString()
  const endpoint = `/api/v1/production/fermentation${queryString ? `?${queryString}` : ''}`
  return fetchApi<FermentationRecord[]>(endpoint, { cache: 'no-store' })
}

export async function getFermentationRecord(id: string) {
  return fetchApi<FermentationRecord>(`/api/v1/production/fermentation/${id}`)
}

export async function createFermentationRecord(data: FermentationFormData) {
  console.log('[createFermentationRecord] received data:', JSON.stringify(data, null, 2))
  const body = JSON.stringify(data)
  console.log('[createFermentationRecord] request body:', body)
  const response = await fetchApi<FermentationRecord>('/api/v1/production/fermentation', {
    method: 'POST',
    body,
  })
  console.log('[createFermentationRecord] response:', JSON.stringify(response))
  revalidatePath('/production/fermentation')
  return response
}

export async function updateFermentationRecord(id: string, data: Partial<FermentationFormData>) {
  const response = await fetchApi<FermentationRecord>(`/api/v1/production/fermentation/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath('/production/fermentation')
  return response
}

export async function updateFermentationStatus(id: string, status: string) {
  const response = await fetchApi<FermentationRecord>(`/api/v1/production/fermentation/${id}/status`, {
    method: 'PUT',
    body: JSON.stringify({ status }),
  })
  revalidatePath('/production/fermentation')
  return response
}

export async function deleteFermentationRecord(id: string) {
  const response = await fetchApi<null>(`/api/v1/production/fermentation/${id}`, {
    method: 'DELETE',
  })
  revalidatePath('/production/fermentation')
  return response
}