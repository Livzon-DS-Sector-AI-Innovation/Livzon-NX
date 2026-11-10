import { randomUUID } from 'node:crypto'
import type { BrowserContext } from '@playwright/test'

type CriticalBusinessRole = 'equipment-reader' | 'equipment-partial' | 'safety-reader' | 'safety-reviewer'

export async function openCriticalBusinessSession(context: BrowserContext, baseURL: string | undefined, role: CriticalBusinessRole) {
  if (!baseURL) throw new Error('Critical business tests require a frontend baseURL')
  const token = `critical-${role}-${randomUUID()}`
  await context.addCookies([{ name: 'auth_token', value: token, url: baseURL }])
  return { Authorization: `Bearer ${token}` }
}
