import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  cookies: vi.fn().mockResolvedValue({
    get: vi.fn().mockReturnValue({ value: 'system-admin-token' }),
  }),
  revalidatePath: vi.fn(),
}))

vi.mock('next/headers', () => ({ cookies: mocks.cookies }))
vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))

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
})
