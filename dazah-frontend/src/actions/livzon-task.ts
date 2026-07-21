'use server'

import { getAuthHeaders } from '@/lib/auth'
import { getServerApiBaseUrl } from '@/lib/server-api'
import type { components } from '@/types/generated/schema'

type AgentToolExecuteRequest = components['schemas']['AgentToolExecuteRequest']

interface AgentConfirmation {
  id: string
  operation: string
  summary: string
  risk_level: string
  status: string
  expires_at: string
}

interface AgentToolExecuteResponse {
  ok: boolean
  operation: string
  data?: unknown
  meta?: Record<string, unknown>
  requires_confirmation?: boolean
  confirmation?: AgentConfirmation | null
}

interface AgentConfirmationExecuteData {
  confirmation: AgentConfirmation
  result: AgentToolExecuteResponse
}

interface ApiEnvelope<T> {
  message?: string
  data?: T
}

const API_BASE = getServerApiBaseUrl()

async function postAgentApi<T>(path: string, body?: unknown): Promise<T> {
  const authHeaders = await getAuthHeaders()
  const response = await fetch(`${API_BASE}/api/v1/agent${path}`, {
    method: 'POST',
    headers: authHeaders,
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: 'no-store',
  })
  const payload = (await response.json()) as ApiEnvelope<T>
  if (!response.ok) {
    throw new Error(payload.message || `请求失败 (${response.status})`)
  }
  return payload.data as T
}

export async function requestLivzonTaskTool(
  input: AgentToolExecuteRequest,
): Promise<AgentToolExecuteResponse> {
  return postAgentApi<AgentToolExecuteResponse>('/tools/execute/user', input)
}

export async function executeLivzonTaskConfirmation(
  confirmationId: string,
): Promise<AgentConfirmationExecuteData> {
  return postAgentApi<AgentConfirmationExecuteData>(
    `/confirmations/${confirmationId}/execute`,
  )
}

export async function cancelLivzonTaskConfirmation(
  confirmationId: string,
): Promise<AgentConfirmation> {
  return postAgentApi<AgentConfirmation>(`/confirmations/${confirmationId}/cancel`)
}
