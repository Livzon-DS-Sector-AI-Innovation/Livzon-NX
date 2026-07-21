export type LocalLoginMode = 'disabled' | 'admin_only' | 'enabled'

export function getLocalLoginMode(): LocalLoginMode {
  const configured = process.env.LOCAL_LOGIN_MODE?.trim().toLowerCase()
  if (
    configured === 'disabled' ||
    configured === 'admin_only' ||
    configured === 'enabled'
  ) {
    return configured
  }
  return process.env.NODE_ENV === 'production' ? 'disabled' : 'enabled'
}
