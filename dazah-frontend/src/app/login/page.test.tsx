import { beforeEach, describe, expect, it, vi } from 'vitest'

const auth = vi.hoisted(() => ({ getCurrentUser: vi.fn(), redirect: vi.fn() }))
vi.mock('@/actions/auth', () => ({ getCurrentUser: auth.getCurrentUser }))
vi.mock('next/navigation', () => ({ redirect: auth.redirect }))

import LoginPage from './page'

describe('authenticated login return', () => {
  beforeEach(() => {
    auth.redirect.mockReset().mockImplementation(() => { throw new Error('redirect') })
  })

  it('keeps an energy task link when the existing session is already authenticated', async () => {
    auth.getCurrentUser.mockResolvedValue({ role: 'admin' })
    const next = '/energy/entry?task=task-1&source=feishu'
    await expect(LoginPage({ searchParams: Promise.resolve({ next }) })).rejects.toThrow('redirect')
    expect(auth.redirect).toHaveBeenCalledWith(next)
  })

  it('uses the permitted fallback for an unauthorized task link', async () => {
    auth.getCurrentUser.mockResolvedValue({ role: 'user', page_permissions: [] })
    await expect(LoginPage({ searchParams: Promise.resolve({ next: '/energy/entry?task=other' }) })).rejects.toThrow('redirect')
    expect(auth.redirect).toHaveBeenCalledWith('/no-access')
  })
})
