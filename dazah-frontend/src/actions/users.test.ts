import { afterEach, expect, it, vi } from 'vitest'

vi.mock('@/lib/auth', () => ({ getAuthHeaders: vi.fn(async () => ({ Authorization: 'Bearer test-session' })) }))
vi.mock('@/lib/server-api', () => ({ getServerApiBaseUrl: () => 'http://backend.test' }))
vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))

import { replaceUserPagePermissions, syncFeishuUsers } from './users'

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
