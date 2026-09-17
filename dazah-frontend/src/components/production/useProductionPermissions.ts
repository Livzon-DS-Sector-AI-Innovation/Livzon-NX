'use client'

import { useAuthStore, type AuthUser } from '@/stores/auth'

/**
 * Stable page identities shared by production routes and the backend page
 * permission catalog.  Nested workshop pages intentionally inherit the
 * workshop leaf identity; the backend uses the same mapping for their APIs.
 */
export const PRODUCTION_PAGE_KEYS = {
  overview: 'production:overview',
  workshop1011: 'production:batches:workshop-101-1',
  workshop1012: 'production:batches:workshop-101-2',
  workshop1021: 'production:batches:workshop-102-1',
  workshop1022: 'production:batches:workshop-102-2',
  workshop103Phenylalanine: 'production:batches:workshop-103:ws103-phenylalanine',
  workshop103Lovastatin: 'production:batches:workshop-103:ws103-lovastatin',
  workshop2011: 'production:batches:workshop-201-1',
  workshop2012: 'production:batches:workshop-201-2',
  workshop2013: 'production:batches:workshop-201-3',
  workshop202: 'production:batches:workshop-202',
  workshop203: 'production:batches:workshop-203',
  workshop2033: 'production:batches:workshop-203-3',
  salesPlan: 'production:plan:sales-plan',
  scheduling: 'production:plan:scheduling',
  shiftLogDeviation: 'production:shift-log:shift-log-deviation',
  shiftLogQuality: 'production:shift-log:shift-log-quality',
  shiftLogSummary: 'production:shift-log:shift-log-summary',
  shiftLogHandover: 'production:shift-log:shift-log-handover',
  labelVerification: 'production:label-verification',
  pressure: 'production:pressure',
} as const

export type ProductionPageKey = typeof PRODUCTION_PAGE_KEYS[keyof typeof PRODUCTION_PAGE_KEYS]
export type ProductionPermissionLevel = 'access' | 'query' | 'operate'
export type ProductionSensitiveAction =
  | 'approve'
  | 'reject'
  | 'delete'
  | 'bulk_import'
  | 'sensitive_export'
  | 'sync_config'

type ProductionPermissionUser = Pick<AuthUser, 'id' | 'role'> & {
  page_permissions?: ReadonlyArray<{
    page_key: string
    permissions?: ReadonlyArray<ProductionPermissionLevel>
    sensitive_actions?: ReadonlyArray<string>
  }>
}

/** Pure form used by pages and tests; the server remains the final authority. */
export function hasProductionPagePermission(
  user: ProductionPermissionUser | null | undefined,
  pageKey: ProductionPageKey,
  level: ProductionPermissionLevel,
  sensitiveAction?: ProductionSensitiveAction,
): boolean {
  if (!user) return false
  if (user.role === 'admin') return true

  const grant = user.page_permissions?.find((item) => item.page_key === pageKey)
  if (!grant?.permissions?.includes(level)) return false
  if (!sensitiveAction) return true
  return grant.permissions.includes('operate')
    && Boolean(grant.sensitive_actions?.includes(sensitiveAction))
}

export function useProductionPermissions(pageKey: ProductionPageKey) {
  const user = useAuthStore((state) => state.user)
  return {
    authorizationKey: JSON.stringify([
      user?.id,
      user?.role,
      user?.grant_version,
      user?.page_permissions,
    ]),
    canAccess: hasProductionPagePermission(user, pageKey, 'access'),
    canQuery: hasProductionPagePermission(user, pageKey, 'query'),
    canOperate: hasProductionPagePermission(user, pageKey, 'operate'),
    canApprove: hasProductionPagePermission(user, pageKey, 'operate', 'approve'),
    canReject: hasProductionPagePermission(user, pageKey, 'operate', 'reject'),
    canDelete: hasProductionPagePermission(user, pageKey, 'operate', 'delete'),
    canBulkImport: hasProductionPagePermission(user, pageKey, 'operate', 'bulk_import'),
    canExport: hasProductionPagePermission(user, pageKey, 'operate', 'sensitive_export'),
    canSync: hasProductionPagePermission(user, pageKey, 'operate', 'sync_config'),
  }
}
