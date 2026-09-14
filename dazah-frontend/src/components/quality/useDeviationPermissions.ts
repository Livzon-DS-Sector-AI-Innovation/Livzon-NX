'use client'

import { useAuthStore } from '@/stores/auth'

export const DEVIATION_LEDGER_PAGE = 'quality:deviations:deviation-ledger'

export function useDeviationPermissions() {
  const { user, hasPagePermission } = useAuthStore()
  return {
    authorizationKey: JSON.stringify([user?.id, user?.role, user?.grant_version, user?.page_permissions]),
    workflowFieldsReadOnly: Boolean(user),
    canQuery: hasPagePermission(DEVIATION_LEDGER_PAGE, 'query'),
    canOperate: hasPagePermission(DEVIATION_LEDGER_PAGE, 'operate'),
    canDelete: hasPagePermission(DEVIATION_LEDGER_PAGE, 'operate', 'delete'),
    canExport: hasPagePermission(DEVIATION_LEDGER_PAGE, 'operate', 'sensitive_export'),
    canBatchDelete: hasPagePermission(DEVIATION_LEDGER_PAGE, 'operate', 'delete'),
    // Import remains unreviewed; only the system administrator can use it.
    canImport: user?.role === 'admin',
  }
}
