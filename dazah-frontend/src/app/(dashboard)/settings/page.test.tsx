import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getCurrentUser: vi.fn(),
  notFound: vi.fn(() => {
    throw new Error('NOT_FOUND')
  }),
  serverFetchRoles: vi.fn(),
  serverFetchDepartments: vi.fn(),
  serverFetchDeptRules: vi.fn(),
  serverFetchMenus: vi.fn(),
  serverFetchAdminUsers: vi.fn(),
}))

vi.mock('@/actions/auth', () => ({ getCurrentUser: mocks.getCurrentUser }))
vi.mock('next/navigation', () => ({ notFound: mocks.notFound }))
vi.mock('@/components/settings/SettingsAdminClient', () => ({ default: () => null }))
vi.mock('@/lib/api/server/admin', () => ({
  serverFetchRoles: mocks.serverFetchRoles,
  serverFetchDepartments: mocks.serverFetchDepartments,
  serverFetchDeptRules: mocks.serverFetchDeptRules,
  serverFetchMenus: mocks.serverFetchMenus,
  serverFetchAdminUsers: mocks.serverFetchAdminUsers,
}))

import SettingsPage from './page'

describe('settings page access', () => {
  beforeEach(() => vi.clearAllMocks())

  it('does not fetch settings data for an ordinary administrator', async () => {
    mocks.getCurrentUser.mockResolvedValue({ role: 'admin', roles: ['ordinary_admin'] })

    await expect(SettingsPage()).rejects.toThrow('NOT_FOUND')
    expect(mocks.serverFetchRoles).not.toHaveBeenCalled()
    expect(mocks.serverFetchDepartments).not.toHaveBeenCalled()
    expect(mocks.serverFetchAdminUsers).not.toHaveBeenCalled()
  })

  it('loads settings data for a system administrator', async () => {
    mocks.getCurrentUser.mockResolvedValue({ role: 'admin', roles: ['super_admin'] })
    mocks.serverFetchRoles.mockResolvedValue(['role'])
    mocks.serverFetchDepartments.mockResolvedValue(['department'])
    mocks.serverFetchDeptRules.mockResolvedValue(['rule'])
    mocks.serverFetchMenus.mockResolvedValue(['menu'])
    mocks.serverFetchAdminUsers.mockResolvedValue(['user'])

    const result = await SettingsPage()
    expect(result.props.systemPermissions).toEqual({
      roles: ['role'], departments: ['department'], deptRules: ['rule'],
      menus: ['menu'], users: ['user'],
    })
  })
})
