import { afterEach, expect, it, vi } from 'vitest'
import { fetchRoles } from './admin'

afterEach(() => vi.unstubAllGlobals())

it('preserves the role authorization version for page permission edits', async () => {
  const role = { id: 'role-1', name: '查询员', code: 'reader', is_system: false, permissions: [], grant_version: 7 }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 200, message: 'ok', data: [role] }))))
  expect((await fetchRoles())[0].grant_version).toBe(7)
})
