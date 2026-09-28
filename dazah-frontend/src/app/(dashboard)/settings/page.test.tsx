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
}))

vi.mock('@/actions/auth', () => ({ getCurrentUser: mocks.getCurrentUser }))
vi.mock('next/navigation', () => ({ notFound: mocks.notFound }))
vi.mock('@/components/settings/SettingsAdminClient', () => ({ default: () => null }))
vi.mock('@/lib/api/server/admin', () => ({
  serverFetchRoles: mocks.serverFetchRoles,
  serverFetchDepartments: mocks.serverFetchDepartments,
  serverFetchDeptRules: mocks.serverFetchDeptRules,
  serverFetchMenus: mocks.serverFetchMenus,
}))

import SettingsPage from './page'

describe('settings page access', () => {
  beforeEach(() => vi.clearAllMocks())

  it('does not fetch settings data for an ordinary administrator', async () => {
    mocks.getCurrentUser.mockResolvedValue({ role: 'admin', roles: ['ordinary_admin'] })

    await expect(SettingsPage({ searchParams: Promise.resolve({}) })).rejects.toThrow('NOT_FOUND')
    expect(mocks.serverFetchRoles).not.toHaveBeenCalled()
    expect(mocks.serverFetchDepartments).not.toHaveBeenCalled()
  })

  it('loads the default user tab without fetching permission data', async () => {
    mocks.getCurrentUser.mockResolvedValue({ role: 'admin', roles: ['super_admin'] })

    const result = await SettingsPage({ searchParams: Promise.resolve({}) })
    expect(result.props.activeTab).toBe('users')
    expect(result.props.systemPermissions).toBeNull()
    expect(mocks.serverFetchRoles).not.toHaveBeenCalled()
    expect(mocks.serverFetchDepartments).not.toHaveBeenCalled()
  })

  it('loads permission data only for its direct URL', async () => {
    mocks.getCurrentUser.mockResolvedValue({ role: 'admin', roles: ['super_admin'] })
    mocks.serverFetchRoles.mockResolvedValue(['role'])
    mocks.serverFetchDepartments.mockResolvedValue(['department'])
    mocks.serverFetchDeptRules.mockResolvedValue(['rule'])
    mocks.serverFetchMenus.mockRejectedValue(new Error('菜单服务不可用'))

    const result = await SettingsPage({ searchParams: Promise.resolve({ tab: 'permissions' }) })
    expect(result.props.activeTab).toBe('permissions')
    expect(result.props.systemPermissions).toEqual({
      roles: ['role'], departments: ['department'], deptRules: ['rule'],
    })
    expect(mocks.serverFetchMenus).not.toHaveBeenCalled()
    expect(mocks.serverFetchRoles).toHaveBeenCalledOnce()
    expect(mocks.serverFetchDepartments).toHaveBeenCalledOnce()
    expect(mocks.serverFetchDeptRules).toHaveBeenCalledOnce()
  })

  it('propagates permission data failures instead of showing an empty authorization panel', async () => {
    mocks.getCurrentUser.mockResolvedValue({ role: 'admin', roles: ['super_admin'] })
    mocks.serverFetchRoles.mockRejectedValueOnce(new Error('角色服务不可用'))

    await expect(SettingsPage({ searchParams: Promise.resolve({ tab: 'permissions' }) })).rejects.toThrow('角色服务不可用')
    expect(mocks.serverFetchMenus).not.toHaveBeenCalled()
  })
})
