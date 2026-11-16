const PENDING_KEY = 'dazah.impersonation-list.pending'
const RESTORE_KEY = 'dazah.impersonation-list.restore'

export interface ImpersonationListState {
  keyword: string
  roleId: string
  page: number
}

export function saveImpersonationListState(state: ImpersonationListState) {
  try {
    sessionStorage.setItem(PENDING_KEY, JSON.stringify(state))
  } catch {
    // Identity switching can proceed when browser storage is unavailable.
  }
}

export function finishImpersonationListReturn(administratorRestored: boolean) {
  try {
    const pending = sessionStorage.getItem(PENDING_KEY)
    sessionStorage.removeItem(PENDING_KEY)
    if (administratorRestored && pending) {
      sessionStorage.setItem(RESTORE_KEY, pending)
    } else {
      sessionStorage.removeItem(RESTORE_KEY)
    }
  } catch {
    // The destination can load with its default filters.
  }
}

export function takeRestoredImpersonationListState(): ImpersonationListState | undefined {
  try {
    const saved = sessionStorage.getItem(RESTORE_KEY)
    if (!saved) return
    sessionStorage.removeItem(RESTORE_KEY)
    const state: Partial<ImpersonationListState> | null = JSON.parse(saved)
    if (state && typeof state.keyword === 'string' && typeof state.roleId === 'string'
      && typeof state.page === 'number' && Number.isSafeInteger(state.page) && state.page > 0) {
      return { keyword: state.keyword, roleId: state.roleId, page: state.page }
    }
  } catch {
    // Malformed entries and unavailable storage both fall back to the default filters.
  }
}
