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
  it('replaces manual roles with an authorization version and audit reason', async () => {
    const request = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: { message: '角色分配已更新' } })))
    vi.stubGlobal('fetch', request)
    await adminActions.assignUserRoles('user-1', ['role-1', 'role-2'], {
      expectedGrantVersion: 7,
      reason: '岗位职责调整',
    })
    expect(request).toHaveBeenCalledWith(expect.stringContaining('/users/user-1/roles'), expect.objectContaining({
      method: 'POST', body: JSON.stringify({
        role_ids: ['role-1', 'role-2'], mode: 'replace', expected_grant_version: 7, reason: '岗位职责调整',
      }),
    }))
  })

  it('appends deduplicated department roles without replacing current manual roles', async () => {
    const request = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: { message: '角色已分配' } })))
    vi.stubGlobal('fetch', request)
    expect((await adminActions.applyDeptRolesToUser('user-1', ['role-1', 'role-1'])).ok).toBe(true)
    expect(request).toHaveBeenCalledWith(expect.stringContaining('/users/user-1/roles'), expect.objectContaining({
      method: 'POST', body: JSON.stringify({ role_ids: ['role-1'], mode: 'add' }),
    }))
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/system/user-roles')
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/settings')
  })

  it('returns user-specific authorization failures for batch results', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: '管理员不能修改自己的角色' }), { status: 403 })))
    expect(await adminActions.applyDeptRolesToUser('self', ['role-1'])).toEqual({ ok: false, status: 403, message: '管理员不能修改自己的角色' })
    expect(mocks.revalidatePath).not.toHaveBeenCalled()
  })
  it('sends the role authorization version and preserves conflict errors', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ message: '授权版本冲突' }), { status: 409 }))
    vi.stubGlobal('fetch', fetchMock)
    const payload = { expected_grant_version: 3, grants: [], reason: '恢复角色基线' }
    await expect(adminActions.replaceRolePagePermissions('role-1', payload)).resolves.toEqual({ ok: false, status: 409, message: '授权版本冲突' })
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/roles/role-1/page-permissions'), expect.objectContaining({
      method: 'PUT', body: JSON.stringify(payload),
    }))
    expect(mocks.revalidatePath).not.toHaveBeenCalled()
  })

  it('previews role page permission impact without writing grants', async () => {
    const payload = { expected_grant_version: 3, grants: [], reason: '影响预演' }
    const preview = { role_id: 'role-1', member_count: 4, affected_user_count: 2 }
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: preview }), {
      status: 200, headers: { 'content-type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(adminActions.previewRolePagePermissions('role-1', payload)).resolves.toEqual(preview)
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining(
      '/roles/role-1/page-permissions/preview',
    ), expect.objectContaining({ method: 'POST', body: JSON.stringify(payload) }))
    expect(mocks.revalidatePath).not.toHaveBeenCalled()
  })

  it('loads role authorization history, health results and performs a versioned rollback', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: {
        items: [{ id: 'audit-1', grants: [] }], total: 1, page: 1, page_size: 20,
      } })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: { issue_count: 1, issues: [] } })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: { grant_version: 5 } })))
    vi.stubGlobal('fetch', fetchMock)
    await expect(adminActions.getRolePagePermissionHistory('role-1')).resolves.toEqual({
      items: [{ id: 'audit-1', grants: [] }], total: 1, page: 1, page_size: 20,
    })
    await expect(adminActions.getPagePermissionHealth()).resolves.toEqual({ issue_count: 1, issues: [] })
    const payload = { audit_id: 'audit-1', expected_grant_version: 4, reason: '回滚误配权限' }
    await expect(adminActions.rollbackRolePagePermissions('role-1', payload)).resolves.toEqual({ ok: true, data: { grant_version: 5 } })
    expect(fetchMock.mock.calls[2][0]).toEqual(expect.stringContaining('/roles/role-1/page-permissions/rollback'))
    expect(fetchMock.mock.calls[2][1]).toEqual(expect.objectContaining({ method: 'POST', body: JSON.stringify(payload) }))
  })

  it('filters, previews and exports role authorization history', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: [] })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: {
        target_type: 'role', target_id: 'role-1', changes: [], affected_user_count: 0,
      } })))
      .mockResolvedValueOnce(new Response('时间,操作人\n2026-09-16,管理员', {
        headers: { 'Content-Disposition': 'attachment; filename="role-history.csv"' },
      }))
    vi.stubGlobal('fetch', fetchMock)
    await adminActions.getRolePagePermissionHistory('role-1', {
      source: 'rollback', page_key: 'hr:recruitment', actor_user_id: 'actor-1',
      page: 2, page_size: 50,
    })
    expect(fetchMock.mock.calls[0][0]).toEqual(expect.stringContaining(
      'source=rollback&page_key=hr%3Arecruitment&actor_user_id=actor-1&page=2&page_size=50',
    ))
    const previewRequest = { audit_id: 'audit-1', expected_grant_version: 4 }
    await adminActions.previewRolePagePermissionRollback('role-1', previewRequest)
    expect(fetchMock.mock.calls[1][0]).toEqual(expect.stringContaining('/rollback/preview'))
    expect(fetchMock.mock.calls[1][1]).toEqual(expect.objectContaining({
      method: 'POST', body: JSON.stringify(previewRequest),
    }))
    await expect(adminActions.exportRolePagePermissionHistory('role-1')).resolves.toEqual({
      filename: 'role-history.csv', content: '时间,操作人\n2026-09-16,管理员',
    })
  })

  it('sends a versioned permission health remediation request', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      data: { fixed: true, grant_version: 6, message: '已恢复角色基线' },
    })))
    vi.stubGlobal('fetch', fetchMock)
    const payload = {
      code: 'redundant_user_override' as const, target_type: 'user' as const,
      target_id: 'user-1', page_key: 'hr:employee-management:profile',
      expected_grant_version: 5, reason: '健康检查自动修复',
    }
    await expect(adminActions.remediatePagePermissionHealth(payload)).resolves.toEqual({
      ok: true, data: { fixed: true, grant_version: 6, message: '已恢复角色基线' },
    })
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining(
      '/page-permissions/health/remediate',
    ), expect.objectContaining({ method: 'POST', body: JSON.stringify(payload) }))
  })

  it('publishes a page rollout with preview version and confirmation reason', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      data: { module_code: 'hr', status: 'enforced' },
    }), { status: 200, headers: { 'content-type': 'application/json' } }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(adminActions.publishPagePermissionRollout({
      module_code: 'hr', current_version: 4, preview_hash: 'preview-hash',
    } as never, '发布员工页面权限')).resolves.toEqual({
      ok: true, data: { module_code: 'hr', status: 'enforced' },
    })
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining(
      '/identity/admin/page-permissions/modules/hr/publish',
    ), expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({
        expected_version: 4,
        preview_hash: 'preview-hash',
        reason: '发布员工页面权限',
        confirmed: true,
      }),
    }))
  })

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
