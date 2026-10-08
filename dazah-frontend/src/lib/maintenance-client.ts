export type MaintenanceState = { phase: 'normal' | 'announced' | 'maintenance'; starts_at?: number }

export function isMaintenanceActive(state: MaintenanceState): boolean {
  return state.phase === 'maintenance' || (state.phase === 'announced' &&
    typeof state.starts_at === 'number' && state.starts_at <= Date.now() / 1000)
}

export async function readMaintenance(fetcher: typeof fetch): Promise<MaintenanceState | null> {
  const response = await fetcher('/__dazah_maintenance_status', { cache: 'no-store', credentials: 'same-origin' })
  if (response.status === 503 && response.headers.get('X-Dazah-Maintenance') === '1') return { phase: 'maintenance' }
  if (response.status === 204) return { phase: 'normal' }
  if (response.status !== 200) return null
  const data: unknown = await response.json()
  if (data && typeof data === 'object' && 'phase' in data && data.phase === 'announced' &&
    'starts_at' in data && typeof data.starts_at === 'number' && Number.isFinite(data.starts_at)) {
    const state: MaintenanceState = { phase: 'announced', starts_at: data.starts_at }
    return isMaintenanceActive(state) ? { phase: 'maintenance' } : state
  }
  return null
}

/** Stop page requests during release; only the maintenance status probe stays available. */
export function protectFetch(
  original: typeof fetch,
  getState: () => MaintenanceState,
  getSignal: () => AbortSignal,
): typeof fetch {
  return async (input, init) => {
    const request = new Request(typeof input === 'string' ? new URL(input, window.location.href) : input, init)
    const url = new URL(request.url)
    if (url.origin !== window.location.origin || url.pathname === '/__dazah_maintenance_status') return original(input, init)
    if (isMaintenanceActive(getState())) throw new Error('系统正在更新发布，请停止操作，等待维护结束')
    return original(new Request(request, { signal: AbortSignal.any([request.signal, getSignal()]) }))
  }
}
