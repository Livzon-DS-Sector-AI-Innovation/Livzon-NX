import { afterEach, expect, it, vi } from 'vitest'

vi.mock('@/lib/auth', () => ({ getAuthHeaders: vi.fn(async () => ({ Authorization: 'Bearer test-session' })) }))
vi.mock('@/lib/server-api', () => ({ getServerApiBaseUrl: () => 'http://backend.test' }))
vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))

import {
  exportUserPagePermissionHistory, getUserPagePermissionHistory,
  previewUserPagePermissionRollback, replaceUserPagePermissions,
  rollbackUserPagePermissions, syncFeishuUsers,
} from './users'

afterEach(() => vi.unstubAllGlobals())

it('sends an explicit deny, version and reason without inventing grants', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: { grant_version: 5 } })))
  vi.stubGlobal('fetch', fetchMock)
  const payload = { expected_grant_version: 4, reason: '撤销页面权限', grants: [{
    page_key: 'hr:employee-management:profile', mode: 'custom' as const, permissions: [],
  }] }
  await expect(replaceUserPagePermissions('user-1', payload)).resolves.toEqual({ ok: true, data: { grant_version: 5 } })
  expect(fetchMock).toHaveBeenCalledWith('http://backend.test/api/v1/identity/admin/users/user-1/page-permissions', expect.objectContaining({
    method: 'PUT', body: JSON.stringify(payload), headers: expect.objectContaining({ 'If-Match': '4' }),
  }))
})

it('surfaces a stale version as a conflict instead of returning success', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: '授权版本冲突' }), { status: 409 })))
  await expect(replaceUserPagePermissions('user-1', { expected_grant_version: 1, grants: [], reason: '调整' })).resolves.toEqual({ ok: false, status: 409, message: '授权版本冲突' })
})

it('loads authorization history and rolls a user back with the current version', async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ data: {
      items: [{ id: 'audit-1', grants: [] }], total: 1, page: 1, page_size: 20,
    } })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ data: { grant_version: 6 } })))
  vi.stubGlobal('fetch', fetchMock)

  await expect(getUserPagePermissionHistory('user-1')).resolves.toEqual({
    items: [{ id: 'audit-1', grants: [] }], total: 1, page: 1, page_size: 20,
  })
  const payload = { audit_id: 'audit-1', expected_grant_version: 5, reason: '恢复误删授权' }
  await expect(rollbackUserPagePermissions('user-1', payload)).resolves.toEqual({ ok: true, data: { grant_version: 6 } })
  expect(fetchMock.mock.calls[1]).toEqual([
    'http://backend.test/api/v1/identity/admin/users/user-1/page-permissions/rollback',
    expect.objectContaining({ method: 'POST', body: JSON.stringify(payload) }),
  ])
})

it('filters, previews and exports user authorization history', async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ data: [] })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ data: {
      target_type: 'user', target_id: 'user-1', changes: [], affected_user_count: 0,
    } })))
    .mockResolvedValueOnce(new Response('时间,操作人\n2026-09-16,管理员', {
      headers: { 'Content-Disposition': 'attachment; filename="user-history.csv"' },
    }))
  vi.stubGlobal('fetch', fetchMock)
  await getUserPagePermissionHistory('user-1', {
    source: 'manual', page_key: 'hr:recruitment', page: 3, page_size: 10,
  })
  expect(fetchMock.mock.calls[0][0]).toContain(
    'source=manual&page_key=hr%3Arecruitment&page=3&page_size=10',
  )
  const request = { audit_id: 'audit-1', expected_grant_version: 5 }
  await previewUserPagePermissionRollback('user-1', request)
  expect(fetchMock.mock.calls[1]).toEqual([
    'http://backend.test/api/v1/identity/admin/users/user-1/page-permissions/rollback/preview',
    expect.objectContaining({ method: 'POST', body: JSON.stringify(request) }),
  ])
  await expect(exportUserPagePermissionHistory('user-1')).resolves.toEqual({
    filename: 'user-history.csv', content: '时间,操作人\n2026-09-16,管理员',
  })
})

it('syncs Feishu directory users through the authenticated backend endpoint', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
    data: { status: 'ok', message: '同步完成：用户 2 名。' },
  })))
  vi.stubGlobal('fetch', fetchMock)

  await expect(syncFeishuUsers()).resolves.toEqual({
    status: 'ok',
    message: '同步完成：用户 2 名。',
  })
  expect(fetchMock).toHaveBeenCalledWith(
    'http://backend.test/api/v1/identity/users/sync-feishu',
    expect.objectContaining({
      method: 'POST',
      headers: expect.objectContaining({ Authorization: 'Bearer test-session' }),
    }),
  )
})
