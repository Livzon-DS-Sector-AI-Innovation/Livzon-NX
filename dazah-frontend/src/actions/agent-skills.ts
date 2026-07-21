'use server'

import { getServerApiBaseUrl } from '@/lib/server-api'
import { getAuthHeaders } from '@/lib/auth'

const API_BASE = getServerApiBaseUrl()

export interface AgentSkill {
  id: string
  name: string
  title: string
  description: string
  trigger_keywords: string[]
  content: string
  status: string
  is_builtin: boolean
  version: number
  created_at?: string | null
  updated_at?: string | null
}

export interface AgentSkillPayload {
  name: string
  title: string
  description: string
  trigger_keywords: string[]
  content: string
  status?: 'active' | 'disabled'
  is_builtin?: boolean
}

export type AgentSkillUpdatePayload = Partial<Omit<AgentSkillPayload, 'name' | 'is_builtin'>>

interface ApiEnvelope<T> {
  code?: number
  message?: string
  data?: T
}

async function fetchAgentSkillApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const authHeaders = await getAuthHeaders()
  const response = await fetch(`${API_BASE}/api/v1${endpoint}`, {
    ...options,
    headers: {
      ...authHeaders,
      ...options?.headers,
    },
    cache: 'no-store',
  })
  const payload = (await response.json()) as ApiEnvelope<T>
  if (!response.ok) {
    throw new Error(payload.message || `请求失败 (${response.status})`)
  }
  return payload.data as T
}

export async function getAgentSkills() {
  return fetchAgentSkillApi<AgentSkill[]>('/agent/skills')
}

export async function createAgentSkill(payload: AgentSkillPayload) {
  return fetchAgentSkillApi<AgentSkill>('/agent/skills', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function updateAgentSkill(id: string, payload: AgentSkillUpdatePayload) {
  return fetchAgentSkillApi<AgentSkill>(`/agent/skills/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export async function enableAgentSkill(id: string) {
  return fetchAgentSkillApi<AgentSkill>(`/agent/skills/${id}/enable`, {
    method: 'POST',
  })
}

export async function disableAgentSkill(id: string) {
  return fetchAgentSkillApi<AgentSkill>(`/agent/skills/${id}/disable`, {
    method: 'POST',
  })
}

export async function deleteAgentSkill(id: string) {
  return fetchAgentSkillApi<{ ok: boolean }>(`/agent/skills/${id}`, {
    method: 'DELETE',
  })
}
