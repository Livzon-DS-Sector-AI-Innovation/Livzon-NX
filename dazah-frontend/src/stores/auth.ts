'use client'

import { create } from 'zustand'

interface AuthUser {
  id: string
  name: string
  roles?: string[]
  permissions?: string[]
}

interface AuthState {
  user: AuthUser | null
  setUser: (user: AuthUser | null) => void
  clearUser: () => void
  hasPermission: (code: string) => boolean
}

/** Client display state only; backend authorization remains authoritative. */
export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  setUser: (user) => set({ user }),
  clearUser: () => set({ user: null }),
  hasPermission: (code) => {
    const permissions = get().user?.permissions ?? []
    return permissions.includes('*') || permissions.includes(code)
  },
}))
