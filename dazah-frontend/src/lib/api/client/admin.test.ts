import { afterEach, expect, it, vi } from 'vitest'
import { fetchRoles, fetchAdminUsers } from './admin'

afterEach(() => vi.unstubAllGlobals())

it('replaces the expired page with login on unauthorized responses', async () => {
  const replace = vi.fn()
  vi.stubGlobal('window', { location: { replace } })
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 401 })))
  await expect(fetchRoles()).rejects.toThrow('未登录或登录已过期')
  expect(replace).toHaveBeenCalledWith('/login')
})

it('preserves the role authorization version for page permission edits', async () => {
  const role = { id: 'role-1', name: '查询员', code: 'reader', is_system: false, permissions: [], grant_version: 7 }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 200, message: 'ok', data: [role] }))))
  expect((await fetchRoles())[0].grant_version).toBe(7)
})

it('paginates and encodes user searches without changing existing callers', async () => {
  const request = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ data: { items: [], total: 0 } })))
  vi.stubGlobal('fetch', request)
  await fetchAdminUsers({ keyword: '质量 & 管理', offset: 20, limit: 20,
    department_id: 'od-1', department_name: '质量部', user_scope: 'missing' })
  const url = new URL(request.mock.calls[0][0], 'http://localhost')
  expect(url.searchParams.get('keyword')).toBe('质量 & 管理')
  expect(url.searchParams.get('offset')).toBe('20')
  expect(url.searchParams.get('limit')).toBe('20')
  expect(url.searchParams.get('department_id')).toBe('od-1')
  expect(url.searchParams.get('department_name')).toBe('质量部')
  expect(url.searchParams.get('user_scope')).toBe('missing')
  await fetchAdminUsers()
  expect(request).toHaveBeenLastCalledWith('/api/v1/identity/admin/users?limit=500', { cache: 'no-store' })
})
