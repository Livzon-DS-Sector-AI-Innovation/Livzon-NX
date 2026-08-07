'use server'

import { getServerApiBaseUrl } from '@/lib/server-api'
import { getAuthHeaders } from '@/lib/auth'
import type { components } from '@/types/generated/schema'

const API_BASE = getServerApiBaseUrl()

export type LLMConfig = components['schemas']['LLMConfigResponse']
export type LLMConfigFormData = components['schemas']['LLMConfigCreate']
export type LLMConfigUpdate = components['schemas']['LLMConfigUpdate']
export type LLMCapabilityDetection = components['schemas']['LLMCapabilityDetectionResponse']
export type FeishuConfig = components['schemas']['FeishuConfigResponse']
export type FeishuConfigUpsert = components['schemas']['FeishuConfigUpsert']
type FeishuDiagnosticResult = components['schemas']['FeishuDiagnosticResult']
export type FeishuGatewayRestartResult =
  components['schemas']['FeishuGatewayRestartResult']
export type ExternalIdentityBindingCreate =
  components['schemas']['ExternalIdentityBindingCreate']
export interface ExternalIdentityBinding extends ExternalIdentityBindingCreate {
  id: string
  status: 'active' | 'suspended' | 'revoked'
  last_seen_at?: string | null
  verified_at?: string | null
  created_at: string
  updated_at: string
  local_user_name?: string | null
  local_user_department?: string | null
  local_user_status?: string | null
}
export interface ExternalIdentityConflict {
  local_user_id: string
  local_user_name: string
  department?: string | null
  external_identifier: string
  conflict_type: 'external_owned_by_other' | 'local_binding_mismatch'
  conflicting_binding_id: string
}
export interface ExternalIdentityBindingPage {
  items: ExternalIdentityBinding[]
  page: number
  page_size: number
  total: number
}
export interface AgentToolCatalogEntry {
  operation: string
  module?: string | null
  version: string
  summary: string
  status: 'active' | 'disabled'
  risk_level: 'low' | 'medium' | 'high'
  write: boolean
  confirmation_required: boolean
  permission_key?: string | null
  input_schema: Record<string, unknown>
  output_schema: Record<string, unknown>
  timeout_seconds: number
  idempotent: boolean
}
export interface FeishuGatewayStatus {
  configured: boolean
  credential_version: number | null
  config_version: number
  tenant_id: string
  gateway_enabled: boolean
  gateway: string
  gateway_reconnects: number
  outbox_depth: number
  pending_confirmations: number
  pending_deliveries: number
  event_consumer?: string | null
  event_consumer_count?: number
  gateway_upstream?: {
    release_tag?: string
    release_version?: string
    commit_sha?: string
  } | null
}
export interface AgentRuntimeOverview {
  pending_confirmations: number
  failed_deliveries: number
  latest_error_trace_id?: string | null
  latest_error_at?: string | null
}
export interface AgentToolCatalogPage {
  items: AgentToolCatalogEntry[]
  page: number
  page_size: number
  total: number
}
export interface FeishuAuthorization {
  id: string
  user_id: string
  resource: string
  action: string
  risk: string
  created_at: number
  expires_at?: number | null
}
export interface AgentConfirmationGovernanceItem {
  id: string
  session_id?: string | null
  user_id?: string | null
  operation: string
  summary: string
  risk_level: string
  status: string
  expires_at: string
  executed_at?: string | null
  created_at: string
}
export interface AgentTraceResult {
  trace_id: string
  counts: {
    messages: number
    tool_calls: number
    confirmations: number
    domain_events: number
    deliveries: number
    capability_searches: number
    audit_receipts: number
  }
  timeline: Array<{
    type: string
    id: string
    occurred_at: string
    status: string
    summary: string
    operation?: string | null
    error_code?: string | null
    external_message_id?: string | null
    attempt_count?: number
    receipt_id?: string | null
  }>
}

interface ApiResponse<T> {
  code: number
  data: T
  message?: string
}

function getErrorMessage(value: unknown, fallback: string): string {
  if (!value || typeof value !== 'object') return fallback
  const payload = value as { detail?: unknown; message?: unknown }
  if (typeof payload.detail === 'string' && payload.detail) return payload.detail
  if (typeof payload.message === 'string' && payload.message) return payload.message
  return fallback
}

async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<ApiResponse<T>> {
  const authHeaders = await getAuthHeaders()

  const res = await fetch(`${API_BASE}/api/v1${endpoint}`, {
    ...options,
    headers: {
      ...authHeaders,
      ...options?.headers,
    },
    cache: 'no-store',
  })

  if (!res.ok) {
    const fallback = `API error: ${res.status}`
    const errorText = await res.text()
    if (!errorText) {
      throw new Error(fallback)
    }
    try {
      throw new Error(getErrorMessage(JSON.parse(errorText), fallback))
    } catch (error) {
      if (error instanceof SyntaxError) {
        throw new Error(errorText)
      }
      throw error
    }
  }

  if (res.status === 204) {
    return { code: 0, data: null as T }
  }

  const data = await res.json()
  return { code: 0, data }
}

export async function getLLMConfigs(configType?: string) {
  const searchParams = new URLSearchParams()
  if (configType) searchParams.set('config_type', configType)

  const queryString = searchParams.toString()
  const endpoint = `/llm/configs${queryString ? `?${queryString}` : ''}`
  return fetchApi<LLMConfig[]>(endpoint)
}

export async function getLLMConfig(id: string) {
  return fetchApi<LLMConfig>(`/llm/configs/${id}`)
}

export async function createLLMConfig(data: LLMConfigFormData) {
  const response = await fetchApi<LLMConfig>('/llm/configs', {
    method: 'POST',
    body: JSON.stringify(data),
  })
  return response
}

export async function updateLLMConfig(id: string, data: LLMConfigUpdate) {
  const response = await fetchApi<LLMConfig>(`/llm/configs/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  return response
}

export async function deleteLLMConfig(id: string) {
  const response = await fetchApi<null>(`/llm/configs/${id}`, {
    method: 'DELETE',
  })
  return response
}

export async function testLLMConnection() {
  const response = await fetchApi<LLMCapabilityDetection>('/llm/configs/test', {
    method: 'POST',
  })
  return response
}

export async function testLLMConfig(id: string) {
  return fetchApi<LLMCapabilityDetection>(`/llm/configs/${id}/test`, {
    method: 'POST',
  })
}

function unwrapResponseData<T>(value: unknown): T {
  if (
    value &&
    typeof value === 'object' &&
    'data' in value
  ) {
    return (value as { data: T }).data
  }
  return value as T
}

export async function getLivzonFeishuConfig() {
  const response = await fetchApi<unknown>('/identity/feishu-config')
  return unwrapResponseData<FeishuConfig>(response.data)
}

export async function saveLivzonFeishuConfig(data: FeishuConfigUpsert) {
  const response = await fetchApi<unknown>('/identity/feishu-config', {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  return unwrapResponseData<FeishuConfig>(response.data)
}

export async function getLivzonFeishuGatewayStatus() {
  const response = await fetchApi<unknown>(
    '/identity/feishu-config/gateway-status',
  )
  return unwrapResponseData<FeishuGatewayStatus>(response.data)
}

export async function restartLivzonFeishuGateway() {
  const response = await fetchApi<unknown>(
    '/identity/feishu-config/gateway/restart',
    { method: 'POST' },
  )
  return unwrapResponseData<FeishuGatewayRestartResult>(response.data)
}

export async function getExternalIdentityBindings(params: {
  page?: number
  pageSize?: number
  keyword?: string
  tenantId?: string
  status?: string
  department?: string
  activeSince?: string
} = {}) {
  const search = new URLSearchParams({
    page: String(params.page ?? 1),
    page_size: String(params.pageSize ?? 20),
  })
  if (params.keyword) search.set('keyword', params.keyword)
  if (params.tenantId) search.set('tenant_id', params.tenantId)
  if (params.status) search.set('status_value', params.status)
  if (params.department) search.set('department', params.department)
  if (params.activeSince) search.set('active_since', params.activeSince)
  const response = await fetchApi<unknown>(
    `/identity/external-identity-bindings?${search}`,
  )
  return unwrapResponseData<ExternalIdentityBindingPage>(response.data)
}

export async function getExternalIdentityConflicts() {
  const response = await fetchApi<unknown>(
    '/identity/external-identity-bindings/conflicts',
  )
  return unwrapResponseData<ExternalIdentityConflict[]>(response.data)
}

export async function syncLivzonFeishuDirectory() {
  const response = await fetchApi<unknown>('/identity/sync/all', {
    method: 'POST',
  })
  return unwrapResponseData<{
    status: 'ok' | 'warning'
    message: string
    bindings: {
      created: number
      existing: number
      conflicts: ExternalIdentityConflict[]
    }
  }>(response.data)
}

export async function createExternalIdentityBinding(
  data: ExternalIdentityBindingCreate,
) {
  const response = await fetchApi<unknown>(
    '/identity/external-identity-bindings',
    { method: 'POST', body: JSON.stringify(data) },
  )
  return unwrapResponseData<ExternalIdentityBinding>(response.data)
}

export async function updateExternalIdentityBindingStatus(
  bindingId: string,
  status: ExternalIdentityBinding['status'],
) {
  const response = await fetchApi<unknown>(
    `/identity/external-identity-bindings/${encodeURIComponent(bindingId)}/status`,
    { method: 'POST', body: JSON.stringify({ status }) },
  )
  return unwrapResponseData<ExternalIdentityBinding>(response.data)
}

export async function getAgentToolCatalog() {
  const response = await fetchApi<unknown>('/agent/control/tools')
  return unwrapResponseData<AgentToolCatalogEntry[]>(response.data)
}

export async function getAgentToolCatalogPage(params: {
  page?: number
  pageSize?: number
  keyword?: string
  module?: string
  status?: string
  riskLevel?: string
  write?: boolean
} = {}) {
  const search = new URLSearchParams({
    page: String(params.page ?? 1),
    page_size: String(params.pageSize ?? 20),
  })
  if (params.keyword) search.set('keyword', params.keyword)
  if (params.module) search.set('module', params.module)
  if (params.status) search.set('status_value', params.status)
  if (params.riskLevel) search.set('risk_level', params.riskLevel)
  if (params.write !== undefined) search.set('write', String(params.write))
  const response = await fetchApi<unknown>(`/agent/control/tools/page?${search}`)
  return unwrapResponseData<AgentToolCatalogPage>(response.data)
}

export async function setAgentToolEnabled(
  operation: string,
  enabled: boolean,
) {
  const response = await fetchApi<unknown>(
    `/agent/tools/${encodeURIComponent(operation)}/enabled`,
    { method: 'POST', body: JSON.stringify({ enabled }) },
  )
  return unwrapResponseData<AgentToolCatalogEntry>(response.data)
}

export async function testLivzonFeishuConfig(data?: FeishuConfigUpsert) {
  const response = await fetchApi<unknown>('/identity/feishu-config/test', {
    method: 'POST',
    body: JSON.stringify(data || null),
  })
  return unwrapResponseData<FeishuDiagnosticResult>(response.data)
}

export async function getFeishuAuthorizations(userId: string) {
  const response = await fetchApi<unknown>(
    `/identity/feishu-config/authorizations?user_id=${encodeURIComponent(userId)}`,
  )
  const data = unwrapResponseData<{ items: FeishuAuthorization[] }>(response.data)
  return data.items
}

export async function revokeFeishuAuthorization(grantId: string, userId: string) {
  const response = await fetchApi<unknown>(
    `/identity/feishu-config/authorizations/${encodeURIComponent(grantId)}?user_id=${encodeURIComponent(userId)}`,
    { method: 'DELETE' },
  )
  return unwrapResponseData<{ status: string; id: string }>(response.data)
}

export async function getAgentConfirmations(params: {
  page?: number
  pageSize?: number
  status?: string
  userId?: string
} = {}) {
  const search = new URLSearchParams({
    page: String(params.page ?? 1),
    page_size: String(params.pageSize ?? 20),
  })
  if (params.status) search.set('status_value', params.status)
  if (params.userId) search.set('user_id', params.userId)
  const response = await fetchApi<unknown>(`/agent/control/confirmations?${search}`)
  return unwrapResponseData<{
    items: AgentConfirmationGovernanceItem[]
    page: number
    page_size: number
    total: number
  }>(response.data)
}

export async function getAgentTrace(traceId: string) {
  const response = await fetchApi<unknown>(
    `/agent/control/traces/${encodeURIComponent(traceId)}`,
  )
  return unwrapResponseData<AgentTraceResult>(response.data)
}

export async function exportAgentTrace(traceId: string) {
  const authHeaders = await getAuthHeaders()
  const response = await fetch(
    `${API_BASE}/api/v1/agent/control/traces/${encodeURIComponent(traceId)}/export`,
    { headers: authHeaders, cache: 'no-store' },
  )
  if (!response.ok) throw new Error(`Trace 导出失败 (${response.status})`)
  return {
    filename: `livzon-trace-${traceId}.json`,
    content: await response.text(),
  }
}

export async function getAgentRuntimeOverview() {
  const response = await fetchApi<unknown>('/agent/control/runtime-overview')
  return unwrapResponseData<AgentRuntimeOverview>(response.data)
}

export async function getAgentDeliveries(status?: string) {
  const search = new URLSearchParams({ page: '1', page_size: '50' })
  if (status) search.set('status_value', status)
  const response = await fetchApi<unknown>(`/agent/push-deliveries?${search}`)
  return unwrapResponseData<Record<string, unknown>>(response.data)
}

export async function getAgentOperationsHealth() {
  const response = await fetchApi<unknown>('/agent/operations/health')
  return unwrapResponseData<Record<string, unknown>>(response.data)
}

export async function getAgentCapabilityImpacts() {
  const response = await fetchApi<unknown>('/agent/automation-capability-impacts')
  return unwrapResponseData<Array<Record<string, unknown>>>(response.data)
}
