export const IMPERSONATION_COOKIE = 'impersonation_token'
export const IMPERSONATION_RECOVERY_PATH = '/auth/impersonation'
export const IMPERSONATION_SETTINGS_PATH = '/settings?tab=permissions&view=impersonation'

export function getEffectiveToken(cookies: {
  get(name: string): { value: string } | undefined
}): string | undefined {
  const simulation = cookies.get(IMPERSONATION_COOKIE)
  return simulation ? simulation.value : cookies.get('auth_token')?.value
}
