import type { components, operations } from '@/types/generated/schema'
import { IMPERSONATION_RECOVERY_PATH } from '@/lib/impersonation'

export type ImpersonationTarget = components['schemas']['ImpersonationTarget']
type ImpersonationTargetQuery = NonNullable<operations['list_impersonation_targets_api_v1_identity_admin_impersonation_targets_get']['parameters']['query']>

async function requireSuccess(response: Response, fallback: string) {
  if (response.ok) return
  const error: unknown = await response.json().catch(() => null)
  const message = error && typeof error === 'object' && 'message' in error ? error.message : undefined
  const detail = error && typeof error === 'object' && 'detail' in error ? error.detail : undefined
  throw new Error(typeof detail === 'string' ? detail : typeof message === 'string' ? message : fallback)
}

export async function listImpersonationTargets(query: ImpersonationTargetQuery, signal: AbortSignal) {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value != null) params.set(key, String(value))
  }
  const response = await fetch(`/api/v1/identity/admin/impersonation/targets?${params}`, { signal, cache: 'no-store' })
  await requireSuccess(response, '暂时无法查询用户')
  const body: components['schemas']['ApiResponseEnvelope_ImpersonationTargets_'] = await response.json()
  return body.data
}

export async function startImpersonation(targetId: string) {
  const payload: components['schemas']['ImpersonationStart'] = { target_id: targetId }
  const response = await fetch(`${IMPERSONATION_RECOVERY_PATH}/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  await requireSuccess(response, '暂时无法开始模拟')
}

export async function exitImpersonation() {
  const response = await fetch(`${IMPERSONATION_RECOVERY_PATH}/exit`, { method: 'POST' })
  await requireSuccess(response, '暂时无法退出模拟')
  const body: components['schemas']['ApiResponseEnvelope_ImpersonationExit_'] = await response.json()
  return body.data.administrator_restored
}
