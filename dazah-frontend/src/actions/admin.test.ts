import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  cookies: vi.fn().mockResolvedValue({
    get: vi.fn().mockReturnValue({ value: 'system-admin-token' }),
  }),
  revalidatePath: vi.fn(),
}))

vi.mock('next/headers', () => ({ cookies: mocks.cookies }))
vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))

import * as adminActions from './admin'
import { createRole } from './admin'

describe('system permission server actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('forwards role writes with authentication and invalidates the role page', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ data: { id: 'role-1' } }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(createRole({ name: '质量管理员', code: 'quality-admin' } as never)).resolves.toEqual({
      id: 'role-1',
    })

    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/v1/identity/admin/roles')
    expect(fetchMock.mock.calls[0][1]).toEqual(
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ Authorization: 'Bearer system-admin-token' }),
      }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/system/roles')
  })

  it('covers all system permission server-action contracts', async () => {
    const fetchMock = vi.fn().mockImplementation(async (url: string) => {
      if (url.endsWith('/permissions/export')) {
        return new Response('code,name\nquality.read,质量读取\n', {
          status: 200,
          headers: {
            'Content-Disposition': 'attachment; filename=permissions.csv',
          },
        })
      }
      return new Response(JSON.stringify({ data: { ok: true } }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    })
    vi.stubGlobal('fetch', fetchMock)

    await adminActions.createRole({ name: '质量管理员', code: 'quality-admin' } as never)
    await adminActions.updateRole('role-1', { name: '质量负责人' } as never)
    await adminActions.deleteRole('role-1')
    await adminActions.setRolePermissions('role-1', ['quality.read'])
    await adminActions.assignUserRoles('user-1', ['role-1'])
    await adminActions.removeUserRole('user-1', 'role-1')
    await adminActions.createDeptRule({ role_id: 'role-1', feishu_department_id: 'dept-1' } as never)
    await adminActions.deleteDeptRule('rule-1')
    await adminActions.createMenu({ name: '质量', type: 'menu' } as never)
    await adminActions.updateMenu('menu-1', { name: '质量管理' } as never)
    await adminActions.deleteMenu('menu-1')
    await adminActions.setRoleMenus('role-1', ['menu-1'])
    await adminActions.saveRoleDataScope('role-1', 'departments', ['质量部'])
    await adminActions.saveUserDataScope('user-1', 'all', [])
    await adminActions.deleteDataScope('scope-1')
    await adminActions.previewUserPermission('user-1')
    await adminActions.simulatePermission({
      permission_code: 'quality.write',
      method: 'POST',
      path: '/api/v1/quality/capas',
    } as never)
    await expect(adminActions.exportPermissions()).resolves.toEqual({
      filename: 'permissions.csv',
      content: 'code,name\nquality.read,质量读取\n',
    })

    expect(fetchMock).toHaveBeenCalledTimes(18)
    expect(fetchMock.mock.calls.every(([, init]) => {
      const headers = init?.headers as Record<string, string> | undefined
      return headers?.Authorization === 'Bearer system-admin-token'
    })).toBe(true)
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/system/user-roles')
  })

  it('maps action errors without exposing backend response details', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ message: '禁止操作' }), {
        status: 403,
        headers: { 'content-type': 'application/json' },
      }),
    ))

    await expect(adminActions.deleteRole('role-1')).rejects.toThrow('禁止操作')
  })

  it('covers invalid JSON and export error fallback branches', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response('upstream unavailable', { status: 502, statusText: 'Bad Gateway' }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ message: '导出被拒绝' }), { status: 403 }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(adminActions.createRole({ name: '质量管理员', code: 'quality-admin' } as never)).rejects.toThrow('请求失败 (502)')
    await expect(adminActions.exportPermissions()).rejects.toThrow('导出被拒绝')
  })

  it('accepts successful empty responses from role writes', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 200 })))
    await expect(adminActions.createRole({ name: '质量管理员', code: 'quality-admin' } as never)).resolves.toBeNull()
  })
})
