'use client'

import { useAuthStore } from '@/stores/auth'

/** UI-level permission helper. Backend authorization remains authoritative. */
export function usePermission() {
  const user = useAuthStore((state) => state.user)
  const permissions = user?.permissions ?? []

  const has = (code: string): boolean =>
    permissions.includes('*') || permissions.includes(code)

  const hasAny = (codes: string[]): boolean =>
    permissions.includes('*') || codes.some((code) => permissions.includes(code))

  return { has, hasAny, permissions }
}
