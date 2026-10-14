'use client'

import { useAuthStore } from '@/stores/auth'
import { useSyncExternalStore } from 'react'

const subscribe = () => () => {}
const clientReady = () => true
const serverReady = () => false

export const DEVIATION_LEDGER_PAGE = 'quality:deviations:deviation-ledger'

export function useDeviationPermissions() {
  const ready = useSyncExternalStore(subscribe, clientReady, serverReady)
  const { user, hasPagePermission } = useAuthStore()
  return {
    authorizationKey: JSON.stringify([user?.id, user?.role, user?.grant_version, user?.page_permissions]),
    canQuery: ready && hasPagePermission(DEVIATION_LEDGER_PAGE, 'query'),
    canOperate: ready && hasPagePermission(DEVIATION_LEDGER_PAGE, 'operate'),
    canDelete: ready && hasPagePermission(DEVIATION_LEDGER_PAGE, 'operate', 'delete'),
    canExport: ready && hasPagePermission(DEVIATION_LEDGER_PAGE, 'operate', 'sensitive_export'),
    canBatchDelete: ready && hasPagePermission(DEVIATION_LEDGER_PAGE, 'operate', 'delete'),
    // Import remains unreviewed; only the system administrator can use it.
    canImport: ready && user?.role === 'admin',
  }
}
