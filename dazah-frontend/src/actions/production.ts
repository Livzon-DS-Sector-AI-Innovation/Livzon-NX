'use server'

import { getServerApiBaseUrl } from '@/lib/server-api'
import { revalidatePath } from 'next/cache'
import { getAuthHeaders } from '@/lib/auth'
import type { components } from '@/types/generated/schema'
import type {
  Batch,
  BatchMaterial,
  ProductionPlan,
  PlanTask,
  ProcessSpec,
  ProcessStep,
  ProcessParameter,
  ProductionRecord,
  MaterialBalance,
  ProductionFeishuConfig,
  ProductionFeishuConfigUpsert,
  ProductionFeishuConnectivityResult,
  ProductionFeishuTableList,
  ProductionFeishuTablePreview,
  BatchFormData,
  BatchMaterialFormData,
  ProductionPlanFormData,
  PlanTaskFormData,
  ProcessSpecFormData,
  ProcessStepFormData,
  ProcessParameterFormData,
  ProductionRecordFormData,
  BatchQueryParams,
  PlanQueryParams,
  ProcessSpecQueryParams,
  ApiResponse,
} from '@/types/production'

const API_BASE = getServerApiBaseUrl()

type SalesPlanDetail = components['schemas']['SalesPlanDetailResponse']
type SalesPlanDetailCreate = components['schemas']['SalesPlanDetailCreate']
type SalesPlanDetailUpdate = components['schemas']['SalesPlanDetailUpdate']
type ProductionExecutionPlan = components['schemas']['ProductionExecutionPlanResponse']
type ProductionExecutionPlanCreate = components['schemas']['ProductionExecutionPlanCreate']
type ProductionExecutionPlanUpdate = components['schemas']['ProductionExecutionPlanUpdate']
type ProductionFeishuSyncBinding = components['schemas']['ProductionFeishuSyncBindingResponse']
type ProductionFeishuSyncBindingCreate = components['schemas']['ProductionFeishuSyncBindingCreate']
type ProductionFeishuSyncBindingUpdate = components['schemas']['ProductionFeishuSyncBindingUpdate']
type ProductionFeishuSyncExecuteRequest = components['schemas']['ProductionFeishuSyncExecuteRequest']
type ProductionFeishuSyncRun = components['schemas']['ProductionFeishuSyncRunResponse']
type GeneratedProductionFeishuTablePreview = components['schemas']['ProductionFeishuTablePreviewResponse']
type ProcessExecutionRecord = components['schemas']['ProcessExecutionRecordResponse']
type ProcessExecutionRecordCreate = components['schemas']['ProcessExecutionRecordCreate']
type ProcessExecutionRecordUpdate = components['schemas']['ProcessExecutionRecordUpdate']
type BatchProgress = components['schemas']['BatchProgressResponse']
type ProcessDefinition = components['schemas']['ProcessDefinition']
type Fermentation = components['schemas']['FermentationResponse']
type FermentationCreate = components['schemas']['FermentationCreate']
type FermentationUpdate = components['schemas']['FermentationUpdate']
type SeedCulture = components['schemas']['SeedCultureResponse']
type SeedCultureCreate = components['schemas']['SeedCultureCreate']
type SeedCultureUpdate = components['schemas']['SeedCultureUpdate']
type NonConformingEvent = components['schemas']['NonConformingEventResponse']
type NonConformingEventCreate = components['schemas']['NonConformingEventCreate']
type NonConformingEventUpdate = components['schemas']['NonConformingEventUpdate']
type ShiftLog = components['schemas']['ShiftLogResponse']
type ShiftLogCreate = components['schemas']['ShiftLogCreate']
type ShiftLogUpdate = components['schemas']['ShiftLogUpdate']
type ShiftHandover = components['schemas']['ShiftHandoverResponse']
type ShiftHandoverCreate = components['schemas']['ShiftHandoverCreate']
type ShiftHandoverUpdate = components['schemas']['ShiftHandoverUpdate']

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
  const text = await response.text()
  let body: ApiResponse<T> | null = null
  if (text) {
    try {
      body = JSON.parse(text) as ApiResponse<T>
    } catch {
      body = null
    }
  }

  if (body) {
    if (!response.ok && body.code === 200) {
      return {
        ...body,
        code: response.status,
        message: body.message || `请求失败：${response.status}`,
      }
    }
    return body
  }

  return {
    code: response.status || 500,
    message: text || `请求失败：${response.status || 500}`,
    data: null as T,
  }
}

// ============ Batch Actions ============

export async function getBatches(params: BatchQueryParams = {}) {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) searchParams.set('page_size', String(params.page_size))
  if (params.status) searchParams.set('status', params.status)
  if (params.product_code) searchParams.set('product_code', params.product_code)
  if (params.product_name) searchParams.set('product_name', params.product_name)
  if (params.batch_no) searchParams.set('batch_no', params.batch_no)
  if (params.production_line) searchParams.set('production_line', params.production_line)

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
  if (params.status) searchParams.set('status', params.status)
  if (params.plan_month) searchParams.set('plan_month', params.plan_month)

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

// ============ Plan Task Actions ============

export async function getPlanTasks(planId: string) {
  return fetchApi<PlanTask[]>(`/api/v1/production/plans/${planId}/tasks`)
}

export async function createPlanTask(data: PlanTaskFormData & { plan_id: string }) {
  const response = await fetchApi<PlanTask>('/api/v1/production/tasks', {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath(`/production/plan/${data.plan_id}`)
  return response
}

export async function updatePlanTask(id: string, data: Partial<PlanTaskFormData>) {
  return fetchApi<PlanTask>(`/api/v1/production/tasks/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export async function deletePlanTask(id: string) {
  return fetchApi<null>(`/api/v1/production/tasks/${id}`, {
    method: 'DELETE',
  })
}

// ============ Sales Plan Detail Actions ============

export async function getProductionExecutionPlans(params: {
  page?: number
  page_size?: number
  workshop?: string
  product_name?: string
} = {}) {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) searchParams.set('page_size', String(params.page_size))
  if (params.workshop) searchParams.set('workshop', params.workshop)
  if (params.product_name) searchParams.set('product_name', params.product_name)
  const queryString = searchParams.toString()
  return fetchApi<ProductionExecutionPlan[]>(
    `/api/v1/production/execution-plans${queryString ? `?${queryString}` : ''}`,
  )
}

export async function createProductionExecutionPlan(data: ProductionExecutionPlanCreate) {
  const response = await fetchApi<ProductionExecutionPlan>(
    '/api/v1/production/execution-plans',
    { method: 'POST', body: JSON.stringify(data) },
  )
  revalidatePath('/production/plan')
  return response
}

export async function updateProductionExecutionPlan(
  id: string,
  data: ProductionExecutionPlanUpdate,
) {
  const response = await fetchApi<ProductionExecutionPlan>(
    `/api/v1/production/execution-plans/${id}`,
    { method: 'PUT', body: JSON.stringify(data) },
  )
  revalidatePath('/production/plan')
  return response
}

export async function deleteProductionExecutionPlan(id: string) {
  const response = await fetchApi<null>(`/api/v1/production/execution-plans/${id}`, {
    method: 'DELETE',
  })
  revalidatePath('/production/plan')
  return response
}

export async function getSalesPlanDetails(params: {
  page?: number
  page_size?: number
  product_name?: string
} = {}) {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) searchParams.set('page_size', String(params.page_size))
  if (params.product_name) searchParams.set('product_name', params.product_name)

  const queryString = searchParams.toString()
  const endpoint = `/api/v1/production/sales-plan-details${queryString ? `?${queryString}` : ''}`
  return fetchApi<SalesPlanDetail[]>(endpoint)
}

export async function createSalesPlanDetail(data: SalesPlanDetailCreate) {
  const response = await fetchApi<SalesPlanDetail>('/api/v1/production/sales-plan-details', {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/production/plan')
  return response
}

export async function updateSalesPlanDetail(id: string, data: SalesPlanDetailUpdate) {
  const response = await fetchApi<SalesPlanDetail>(`/api/v1/production/sales-plan-details/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath('/production/plan')
  return response
}

export async function deleteSalesPlanDetail(id: string) {
  const response = await fetchApi<null>(`/api/v1/production/sales-plan-details/${id}`, {
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

// ============ Production Feishu Actions ============

export async function getProductionFeishuConfig() {
  return fetchApi<ProductionFeishuConfig>('/api/v1/production/feishu-config')
}

export async function getProductionFeishuConfigs() {
  return fetchApi<ProductionFeishuConfig[]>('/api/v1/production/feishu-configs')
}

export async function saveProductionFeishuConfig(data: ProductionFeishuConfigUpsert) {
  const response = await fetchApi<ProductionFeishuConfig>('/api/v1/production/feishu-config', {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath('/production/feishu-config')
  revalidatePath('/production/batches')
  return response
}

export async function testProductionFeishuConfig(data?: ProductionFeishuConfigUpsert) {
  return fetchApi<ProductionFeishuConnectivityResult>('/api/v1/production/feishu-config/test', {
    method: 'POST',
    body: data ? JSON.stringify(data) : undefined,
  })
}

export async function getProductionFeishuTables() {
  return fetchApi<ProductionFeishuTableList>('/api/v1/production/feishu-config/tables')
}

export async function getProductionFeishuRecords(params: {
  config_id?: string
  table_id?: string
  page_size?: number
  page_token?: string
} = {}) {
  const searchParams = new URLSearchParams()
  if (params.config_id) searchParams.set('config_id', params.config_id)
  if (params.table_id) searchParams.set('table_id', params.table_id)
  if (params.page_size) searchParams.set('page_size', String(params.page_size))
  if (params.page_token) searchParams.set('page_token', params.page_token)
  const queryString = searchParams.toString()
  return fetchApi<GeneratedProductionFeishuTablePreview>(
    `/api/v1/production/feishu-config/records${queryString ? `?${queryString}` : ''}`,
  )
}

export async function getProductionFeishuTablesByConfig(configId?: string) {
  const searchParams = new URLSearchParams()
  if (configId) searchParams.set('config_id', configId)
  const queryString = searchParams.toString()
  return fetchApi<ProductionFeishuTableList>(
    `/api/v1/production/feishu-config/tables${queryString ? `?${queryString}` : ''}`,
  )
}

export async function getProductionFeishuSyncBindings(configId?: string) {
  const searchParams = new URLSearchParams()
  if (configId) searchParams.set('config_id', configId)
  const queryString = searchParams.toString()
  return fetchApi<ProductionFeishuSyncBinding[]>(
    `/api/v1/production/feishu-sync-bindings${queryString ? `?${queryString}` : ''}`,
  )
}

export async function createProductionFeishuSyncBinding(
  data: ProductionFeishuSyncBindingCreate,
) {
  const response = await fetchApi<ProductionFeishuSyncBinding>(
    '/api/v1/production/feishu-sync-bindings',
    { method: 'POST', body: JSON.stringify(data) },
  )
  revalidatePath('/production/feishu-config')
  return response
}

export async function updateProductionFeishuSyncBinding(
  bindingId: string,
  data: ProductionFeishuSyncBindingUpdate,
) {
  const response = await fetchApi<ProductionFeishuSyncBinding>(
    `/api/v1/production/feishu-sync-bindings/${bindingId}`,
    { method: 'PUT', body: JSON.stringify(data) },
  )
  revalidatePath('/production/feishu-config')
  return response
}

export async function deleteProductionFeishuSyncBinding(bindingId: string) {
  const response = await fetchApi<null>(
    `/api/v1/production/feishu-sync-bindings/${bindingId}`,
    { method: 'DELETE' },
  )
  revalidatePath('/production/feishu-config')
  return response
}

export async function previewProductionFeishuSyncBinding(
  bindingId: string,
  pageSize = 20,
) {
  return fetchApi<ProductionFeishuTablePreview>(
    `/api/v1/production/feishu-sync-bindings/${bindingId}/preview?page_size=${pageSize}`,
  )
}

export async function getProductionFeishuSyncRuns(bindingId: string) {
  return fetchApi<ProductionFeishuSyncRun[]>(
    `/api/v1/production/feishu-sync-bindings/${bindingId}/runs`,
  )
}

export async function executeProductionFeishuSyncBinding(
  bindingId: string,
  data: ProductionFeishuSyncExecuteRequest,
) {
  const response = await fetchApi<ProductionFeishuSyncRun>(
    `/api/v1/production/feishu-sync-bindings/${bindingId}/sync`,
    { method: 'POST', body: JSON.stringify(data) },
  )
  revalidatePath('/production/feishu-config')
  revalidatePath('/production/plan')
  return response
}

// ============ 203 Workshop Process Execution Actions ============

export async function getProcessExecutionRecords(params: {
  page?: number
  page_size?: number
  batch_no?: string
  workshop_code?: string
  process_code?: string
  status?: string
} = {}) {
  const searchParams = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') searchParams.set(key, String(value))
  })
  const query = searchParams.toString()
  return fetchApi<ProcessExecutionRecord[]>(
    `/api/v1/production/process-records${query ? `?${query}` : ''}`,
  )
}

export async function getProcessCatalog() {
  return fetchApi<ProcessDefinition[]>('/api/v1/production/process-catalog')
}

export async function createProcessExecutionRecord(data: ProcessExecutionRecordCreate) {
  const response = await fetchApi<ProcessExecutionRecord>(
    '/api/v1/production/process-records',
    { method: 'POST', body: JSON.stringify(data) },
  )
  revalidatePath('/production/workshop-203')
  return response
}

export async function updateProcessExecutionRecord(
  recordId: string,
  data: ProcessExecutionRecordUpdate,
) {
  const response = await fetchApi<ProcessExecutionRecord>(
    `/api/v1/production/process-records/${recordId}`,
    { method: 'PUT', body: JSON.stringify(data) },
  )
  revalidatePath('/production/workshop-203')
  return response
}

export async function completeProcessExecutionRecord(recordId: string) {
  const response = await fetchApi<ProcessExecutionRecord>(
    `/api/v1/production/process-records/${recordId}/complete`,
    { method: 'POST' },
  )
  revalidatePath('/production/workshop-203')
  return response
}

export async function deleteProcessExecutionRecord(recordId: string) {
  const response = await fetchApi<null>(
    `/api/v1/production/process-records/${recordId}`,
    { method: 'DELETE' },
  )
  revalidatePath('/production/workshop-203')
  return response
}

export async function getBatchProgress(workshopCode = '203', batchNo?: string) {
  const searchParams = new URLSearchParams({ workshop_code: workshopCode })
  if (batchNo) searchParams.set('batch_no', batchNo)
  return fetchApi<BatchProgress>(
    `/api/v1/production/batch-progress?${searchParams.toString()}`,
  )
}

// ============ Fermentation and Shift Operations ============

function operationQuery(params: Record<string, string | number | undefined>) {
  const searchParams = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') searchParams.set(key, String(value))
  })
  const query = searchParams.toString()
  return query ? `?${query}` : ''
}

export async function getFermentations(params: { batch_no?: string; status?: string } = {}) {
  return fetchApi<Fermentation[]>(`/api/v1/production/fermentations${operationQuery(params)}`)
}

export async function createFermentation(data: FermentationCreate) {
  const response = await fetchApi<Fermentation>('/api/v1/production/fermentations', {
    method: 'POST', body: JSON.stringify(data),
  })
  revalidatePath('/production/fermentation')
  return response
}

export async function updateFermentation(id: string, data: FermentationUpdate) {
  const response = await fetchApi<Fermentation>(`/api/v1/production/fermentations/${id}`, {
    method: 'PUT', body: JSON.stringify(data),
  })
  revalidatePath('/production/fermentation')
  return response
}

export async function deleteFermentation(id: string) {
  const response = await fetchApi<null>(`/api/v1/production/fermentations/${id}`, { method: 'DELETE' })
  revalidatePath('/production/fermentation')
  return response
}

export async function getSeedCultures(params: { batch_no?: string; status?: string } = {}) {
  return fetchApi<SeedCulture[]>(`/api/v1/production/seed-cultures${operationQuery(params)}`)
}

export async function createSeedCulture(data: SeedCultureCreate) {
  const response = await fetchApi<SeedCulture>('/api/v1/production/seed-cultures', {
    method: 'POST', body: JSON.stringify(data),
  })
  revalidatePath('/production/fermentation')
  return response
}

export async function updateSeedCulture(id: string, data: SeedCultureUpdate) {
  const response = await fetchApi<SeedCulture>(`/api/v1/production/seed-cultures/${id}`, {
    method: 'PUT', body: JSON.stringify(data),
  })
  revalidatePath('/production/fermentation')
  return response
}

export async function deleteSeedCulture(id: string) {
  const response = await fetchApi<null>(`/api/v1/production/seed-cultures/${id}`, { method: 'DELETE' })
  revalidatePath('/production/fermentation')
  return response
}

export async function getNonConformingEvents(params: { workshop?: string; status?: string } = {}) {
  return fetchApi<NonConformingEvent[]>(`/api/v1/production/non-conforming-events${operationQuery(params)}`)
}

export async function createNonConformingEvent(data: NonConformingEventCreate) {
  const response = await fetchApi<NonConformingEvent>('/api/v1/production/non-conforming-events', {
    method: 'POST', body: JSON.stringify(data),
  })
  revalidatePath('/production/shift-log')
  return response
}

export async function updateNonConformingEvent(id: string, data: NonConformingEventUpdate) {
  const response = await fetchApi<NonConformingEvent>(`/api/v1/production/non-conforming-events/${id}`, {
    method: 'PUT', body: JSON.stringify(data),
  })
  revalidatePath('/production/shift-log')
  return response
}

export async function closeNonConformingEvent(id: string) {
  const response = await fetchApi<NonConformingEvent>(`/api/v1/production/non-conforming-events/${id}/close`, { method: 'POST' })
  revalidatePath('/production/shift-log')
  return response
}

export async function getShiftLogs(params: { workshop?: string; shift?: string } = {}) {
  return fetchApi<ShiftLog[]>(`/api/v1/production/shift-logs${operationQuery(params)}`)
}

export async function createShiftLog(data: ShiftLogCreate) {
  const response = await fetchApi<ShiftLog>('/api/v1/production/shift-logs', {
    method: 'POST', body: JSON.stringify(data),
  })
  revalidatePath('/production/shift-log')
  return response
}

export async function updateShiftLog(id: string, data: ShiftLogUpdate) {
  const response = await fetchApi<ShiftLog>(`/api/v1/production/shift-logs/${id}`, {
    method: 'PUT', body: JSON.stringify(data),
  })
  revalidatePath('/production/shift-log')
  return response
}

export async function getShiftHandovers(params: { workshop?: string; status?: string } = {}) {
  return fetchApi<ShiftHandover[]>(`/api/v1/production/shift-handovers${operationQuery(params)}`)
}

export async function createShiftHandover(data: ShiftHandoverCreate) {
  const response = await fetchApi<ShiftHandover>('/api/v1/production/shift-handovers', {
    method: 'POST', body: JSON.stringify(data),
  })
  revalidatePath('/production/shift-log')
  return response
}

export async function updateShiftHandover(id: string, data: ShiftHandoverUpdate) {
  const response = await fetchApi<ShiftHandover>(`/api/v1/production/shift-handovers/${id}`, {
    method: 'PUT', body: JSON.stringify(data),
  })
  revalidatePath('/production/shift-log')
  return response
}

export async function confirmShiftHandover(id: string) {
  const response = await fetchApi<ShiftHandover>(`/api/v1/production/shift-handovers/${id}/confirm`, { method: 'POST' })
  revalidatePath('/production/shift-log')
  return response
}
