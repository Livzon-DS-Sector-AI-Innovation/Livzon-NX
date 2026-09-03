import { afterEach, expect, it, vi } from 'vitest'
import { NextRequest } from 'next/server'
import { proxy } from './proxy'

vi.mock('@/lib/server-api', () => ({ getServerApiBaseUrl: () => 'http://backend.test' }))
afterEach(() => vi.unstubAllGlobals())

function me(permissions: string[], status = 'enforced', role = 'user') {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: {
    role, module_codes: ['hr'], page_permission_rollouts: { hr: status },
    page_permissions: [{ page_key: 'hr:employee-management:profile', module_code: 'hr', permissions }],
  } }))))
}

it('blocks unauthorized and access-only pages before Server Components can execute', async () => {
  me([])
  const denied = await proxy(new NextRequest('http://frontend.test/hr/profile'))
  expect(denied.status).toBe(403)
  expect(denied.headers.get('x-middleware-next')).toBeNull()
  me(['access'])
  const accessOnly = await proxy(new NextRequest('http://frontend.test/hr/profile'))
  expect(accessOnly.status).toBe(403)
  expect(await accessOnly.text()).toContain('尚未获得查询数据权限')
})

it('lets a query-authorized page render with server-supplied context', async () => {
  me(['access', 'query'])
  const response = await proxy(new NextRequest('http://frontend.test/hr/profile'))
  expect(response.headers.get('x-middleware-next')).toBe('1')
  expect(response.headers.get('x-middleware-request-x-dazah-page-path')).toBe('/hr/profile')
})

it('derives module landing from an authorized child and preserves draft routing', async () => {
  me(['access', 'query'])
  expect((await proxy(new NextRequest('http://frontend.test/hr'))).headers.get('location'))
    .toBe('http://frontend.test/hr/employee-management')
  me([], 'draft')
  expect((await proxy(new NextRequest('http://frontend.test/hr/profile'))).headers.get('x-middleware-next')).toBe('1')
})

it('fails closed when authorization cannot be checked', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
  expect((await proxy(new NextRequest('http://frontend.test/hr/profile'))).status).toBe(503)
})

it('allows the system administrator to render without explicit page grants', async () => {
  me([], 'enforced', 'admin')
  expect((await proxy(new NextRequest('http://frontend.test/hr/profile'))).headers.get('x-middleware-next')).toBe('1')
})
