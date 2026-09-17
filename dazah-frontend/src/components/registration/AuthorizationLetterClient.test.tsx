/* @vitest-environment happy-dom */

import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import AuthorizationLetterClient from './AuthorizationLetterClient'

const flags = vi.hoisted(() => ({ canOperate: false, canDelete: false, canExport: false }))
vi.mock('@/hooks/usePagePermissions', () => ({ usePagePermissions: () => flags }))
vi.mock('@/components/registration', () => ({ AuthorizationLetterDashboard: () => null }))
vi.mock('@/actions/registration', () => ({
  createAuthorizationFdaEntry: vi.fn(), createAuthorizationLedgerMain: vi.fn(),
  createAuthorizationLedgerUpdate: vi.fn(), deleteAuthorizationFdaEntry: vi.fn(),
  deleteAuthorizationLedgerMain: vi.fn(), deleteAuthorizationLedgerUpdate: vi.fn(),
  updateAuthorizationFdaEntry: vi.fn(), updateAuthorizationLedgerMain: vi.fn(),
  updateAuthorizationLedgerUpdate: vi.fn(),
}))
vi.mock('@/lib/api/client/registration', () => ({ fetchAuthorizationFdaExport: vi.fn(), fetchAuthorizationLedgerExport: vi.fn() }))

describe('registration authorization-letter action grants', () => {
  it.each([false, true])('separates ordinary editing from sensitive export: %s', (canOperate) => {
    Object.assign(flags, { canOperate, canDelete: false, canExport: false })
    const container = document.createElement('div')
    container.innerHTML = renderToStaticMarkup(<AuthorizationLetterClient initialRecords={[]} initialFdaRecords={[]} />)
    const button = (label: string) => Array.from(container.querySelectorAll('button')).find(item => item.textContent?.replace(/\s/g, '') === label)
    expect(button('新增FDA授权')?.disabled).toBe(!canOperate)
    expect(button('新增市场授权')?.disabled).toBe(!canOperate)
    expect(button('导出FDA授权')?.disabled).toBe(true)
    expect(button('导出市场授权')?.disabled).toBe(true)
  })
})
