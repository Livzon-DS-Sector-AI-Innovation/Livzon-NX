import type { User } from '@/types/user'

export function isSystemAdministrator(user: Pick<User, 'role' | 'roles'>): boolean {
  return user.role === 'admin' && !user.roles?.includes('ordinary_admin')
}

export function isSystemSettingsPath(pathname: string): boolean {
  return pathname === '/settings' || pathname.startsWith('/settings/')
    || pathname === '/system' || pathname.startsWith('/system/')
}
