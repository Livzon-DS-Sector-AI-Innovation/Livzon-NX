import type { components } from '@/types/generated/schema'

export type MaintenanceState = { phase: 'normal' | 'announced' | 'maintenance'; starts_at?: number }
export type ProtectedOperation = { id: string; uncertain: boolean; settled?: boolean }

async function confirmedRead(fetcher: typeof fetch, id: string): Promise<boolean> {
  try {
    const response = await fetcher(`/api/v1/system/operations/${id}`, { cache: 'no-store', credentials: 'same-origin' })
    if (!response.ok) return false
    const data = await response.json() as components['schemas']['OperationResult']
    return data.operation_id === id && Array.isArray(data.receipts) && data.receipts.length > 0 &&
      data.receipts.every(receipt => ['GET', 'HEAD', 'OPTIONS'].includes(receipt.method) && ['completed', 'rejected'].includes(receipt.state))
  } catch { return false }
}

function operationId(): string {
  if (crypto.randomUUID) return crypto.randomUUID()
  // LAN HTTP pages lack secure-context-only randomUUID/subtle, but still
  // provide cryptographically secure getRandomValues.
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 15) | 64
  bytes[8] = (bytes[8] & 63) | 128
  const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

async function submissionFingerprint(value: string): Promise<string> {
  if (crypto.subtle) {
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value))
    return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('')
  }
  // This in-memory duplicate hint is not an authentication or integrity proof.
  // A collision only refuses another submission until the user reconciles it.
  return [2166136261, 2246822519, 3266489917, 668265263].map(seed => {
    let hash = seed
    for (let index = 0; index < value.length; index++) hash = Math.imul(hash ^ value.charCodeAt(index), 16777619)
    return (hash >>> 0).toString(16).padStart(8, '0')
  }).join('')
}

export async function readMaintenance(fetcher: typeof fetch): Promise<MaintenanceState | null> {
  const response = await fetcher('/__dazah_maintenance_status', { cache: 'no-store', credentials: 'same-origin' })
  if (response.status === 503 && response.headers.get('X-Dazah-Maintenance') === '1') return { phase: 'maintenance' }
  if (response.status === 204) return { phase: 'normal' }
  if (response.status !== 200) return null
  const data: unknown = await response.json()
  if (data && typeof data === 'object' && 'phase' in data && data.phase === 'announced' &&
    'starts_at' in data && typeof data.starts_at === 'number' && Number.isFinite(data.starts_at)) {
    return { phase: 'announced', starts_at: data.starts_at }
  }
  return null
}

/** No form values, tokens or response bodies are stored; receipts stay in memory. */
export function protectFetch(
  original: typeof fetch,
  getState: () => MaintenanceState,
  operations: Map<string, ProtectedOperation>,
  onChange: () => void,
): typeof fetch {
  const pending = new Map<string, Promise<Response>>()
  return async (input, init) => {
    const request = new Request(typeof input === 'string' ? new URL(input, window.location.href) : input, init)
    const url = new URL(request.url, window.location.href)
    const sameOrigin = url.origin === window.location.origin
    const business = sameOrigin && (url.pathname.startsWith('/api/') || request.headers.has('Next-Action'))
    if (!business) return original(input, init)
    const write = !['GET', 'HEAD', 'OPTIONS'].includes(request.method)
    if (getState().phase === 'maintenance' && !url.pathname.startsWith('/api/v1/system/operations/')) {
      throw new Error('系统维护中，页面输入已保留，本次操作未发送')
    }
    if (!write) return original(input, init)
    // Bound fingerprint memory. Uploads have a distinct transport ID and must
    // be reconciled before retrying; their file contents are never retained.
    const action = `${request.method}:${url.pathname}:${url.search}:${request.headers.get('Next-Action') || ''}`
    // Bodies too large or opaque to fingerprint block subsequent calls to the
    // same action until reconciliation, rather than silently assigning a new ID.
    let fingerprint = action
    let fingerprintBody = typeof init?.body === 'string' ? init.body : null
    if (init?.body instanceof FormData) {
      fingerprintBody = JSON.stringify(Array.from(init.body.entries(), ([name, value]) => [name,
        typeof value === 'string' ? value : { name: value.name, size: value.size, type: value.type },
      ]))
    }
    if (fingerprintBody !== null && fingerprintBody.length <= 2 * 1024 * 1024) {
      fingerprint = await submissionFingerprint(`${action}:${fingerprintBody}`)
    }
    const previous = operations.get(fingerprint)
    if (previous) {
      const inFlight = pending.get(fingerprint)
      // Concurrent identical Actions share one transport, including read-only
      // Effects in Strict Mode. Each caller receives its own response stream.
      if (!previous.settled && inFlight) return (await inFlight).clone()
      // A confirmed read can be refreshed after a lost transport. Writes and
      // missing records always keep their guard until explicit reconciliation.
      if (!previous.settled || !await confirmedRead(original, previous.id)) {
        throw new Error('本次操作结果尚未核对，请先查询操作结果，不要重复提交')
      }
      operations.delete(fingerprint)
    }
    if (getState().phase === 'maintenance') {
      throw new Error('系统维护中，页面输入已保留，本次操作未发送')
    }
    const operation: ProtectedOperation = { id: operationId(), uncertain: true, settled: false }
    operations.set(fingerprint, operation)
    onChange()
    request.headers.set('X-Dazah-Operation-ID', operation.id)
    const confirmActionResponse = async (response: Response) => {
      try {
        // Read and discard a bounded clone without saving the response body.
        // Headers alone do not prove that a streamed Action result arrived.
        const reader = response.clone().body?.getReader()
        if (!reader) return
        let size = 0
        while (true) {
          const chunk = await reader.read()
          if (chunk.done) break
          size += chunk.value.byteLength
          if (size > 2 * 1024 * 1024) { void reader.cancel().catch(() => {}); return }
        }
        if (operations.get(fingerprint) !== operation) return
        if (await confirmedRead(original, operation.id) && operations.get(fingerprint) === operation) operations.delete(fingerprint)
      } catch { /* Unknown delivery or lookup keeps the duplicate guard. */ }
      finally { onChange() }
    }
    try {
      const transport = original(request)
      pending.set(fingerprint, transport)
      const response = await transport
      operation.settled = true
      operation.uncertain = !response.ok || request.headers.has('Next-Action')
      // Actions can return HTTP 200 with an application failure. Verify full
      // delivery and backend receipts before allowing another explicit intent.
      if (!operation.uncertain) operations.delete(fingerprint)
      else if (response.ok && request.headers.has('Next-Action')) void confirmActionResponse(response)
      onChange()
      return response
    } catch (error) {
      operation.settled = true
      operation.uncertain = true
      onChange()
      throw error
    } finally { pending.delete(fingerprint) }
  }
}
