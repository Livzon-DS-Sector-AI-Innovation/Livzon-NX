'use client'

import { usePathname } from 'next/navigation'
import { getPageKeyByPath } from '@/lib/menu-config'
import { useAuthStore, type AuthUser } from '@/stores/auth'

export function pagePermissionFlags(user: AuthUser | null, pageKey: string | undefined) {
  const grant = user?.page_permissions?.find((item) => item.page_key === pageKey)
  const administrator = user?.role === 'admin'
  const canQuery = administrator || Boolean(grant?.permissions?.includes('query'))
  const canOperate = administrator || Boolean(grant?.permissions?.includes('operate'))
  const action = (key: string) => administrator || (canOperate && Boolean(grant?.sensitive_actions?.includes(key)))
  return {
    pageKey,
    canAccess: administrator || Boolean(grant?.permissions?.includes('access')),
    canQuery,
    canOperate,
    canDelete: action('delete'),
    canExport: action('sensitive_export'),
    canImport: action('bulk_import'),
    canSync: action('sync_config'),
    canApprove: action('approve'),
    canReject: action('reject'),
  }
}

/** Page grants are authoritative even when a user retains legacy module roles. */
export function usePagePermissions(pageKey?: string) {
  const pathname = usePathname()
  const user = useAuthStore((state) => state.user)
  return pagePermissionFlags(user, pageKey ?? getPageKeyByPath(pathname))
}
