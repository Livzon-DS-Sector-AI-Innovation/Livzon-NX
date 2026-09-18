import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getCurrentUser: vi.fn(),
  notFound: vi.fn(() => {
    throw new Error('NOT_FOUND')
  }),
}))

vi.mock('@/actions/auth', () => ({ getCurrentUser: mocks.getCurrentUser }))
vi.mock('next/navigation', () => ({ notFound: mocks.notFound }))

import SystemSettingsLayout from './layout'

describe('system settings layout access', () => {
  beforeEach(() => vi.clearAllMocks())

  it('rejects anonymous and ordinary administrator visits', async () => {
    mocks.getCurrentUser.mockResolvedValueOnce(null)
    await expect(SystemSettingsLayout({ children: 'settings' })).rejects.toThrow('NOT_FOUND')

    mocks.getCurrentUser.mockResolvedValueOnce({ role: 'admin', roles: ['ordinary_admin'] })
    await expect(SystemSettingsLayout({ children: 'settings' })).rejects.toThrow('NOT_FOUND')
    expect(mocks.notFound).toHaveBeenCalledTimes(2)
  })

  it('renders system settings for a system administrator', async () => {
    mocks.getCurrentUser.mockResolvedValue({ role: 'admin', roles: ['super_admin'] })
    await expect(SystemSettingsLayout({ children: 'settings' })).resolves.toBe('settings')
    expect(mocks.notFound).not.toHaveBeenCalled()
  })
})
