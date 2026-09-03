'use client'

import { create } from 'zustand'
import { getModuleByKey } from '@/lib/menu-config'
import type { User } from '@/types/user'

interface AuthUser {
  id: string
  name: string
  role?: string
  roles?: string[]
  permissions?: string[]
  page_permissions?: User['page_permissions']
  page_permission_rollouts?: User['page_permission_rollouts']
  grant_version?: User['grant_version']
}

interface AuthState {
  user: AuthUser | null
  setUser: (user: AuthUser | null) => void
  clearUser: () => void
  hasPermission: (code: string) => boolean
  hasPagePermission: (pageKey: string, level: 'access' | 'query' | 'operate', sensitiveAction?: string) => boolean
}

/** Client display state only; backend authorization remains authoritative. */
export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  setUser: (user) => set({ user }),
  clearUser: () => set({ user: null }),
  hasPermission: (code) => {
    if (get().user?.role === 'admin') return true
    const permissions = get().user?.permissions ?? []
    return permissions.includes('*') || permissions.includes(code)
  },
  hasPagePermission: (pageKey, level, sensitiveAction) => {
    const user = get().user
    if (!user) return false
    const currentModule = getModuleByKey(pageKey.split(':')[0])
    if (!currentModule) return false
    if (user.role === 'admin') return true
    if (user.page_permission_rollouts?.[currentModule.moduleCode] !== 'enforced') return true
    const grant = user.page_permissions?.find((item) => item.page_key === pageKey)
    return Boolean(grant?.permissions?.includes(level)
      && (!sensitiveAction || (grant.permissions.includes('operate') && grant.sensitive_actions?.includes(sensitiveAction))))
  },
}))
