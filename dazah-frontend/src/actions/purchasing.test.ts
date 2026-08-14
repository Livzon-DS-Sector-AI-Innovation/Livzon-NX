import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getServerToken: vi.fn().mockResolvedValue('server-token'),
  revalidatePath: vi.fn(),
}))

vi.mock('@/lib/auth', () => ({ getServerToken: mocks.getServerToken }))
vi.mock('@/lib/server-api', () => ({
  getServerApiBaseUrl: () => 'http://backend.test',
}))
vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))

import {
  saveProcurementMaterialSource,
  testProcurementMaterialSource,
} from './purchasing'

const payload = {
  source_url: 'https://feishu.cn/base/app-token?table=table-id',
}

describe('procurement material source actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('tests and saves the material source through authenticated backend calls', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ code: 200, message: 'success', data: { status: 'success' } }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ code: 200, message: 'success', data: { id: 'config-1' } }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
      )
    vi.stubGlobal('fetch', fetchMock)

    await expect(testProcurementMaterialSource(payload)).resolves.toMatchObject({ code: 200 })
    await expect(saveProcurementMaterialSource(payload)).resolves.toMatchObject({ code: 200 })

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      'http://backend.test/api/v1/procurement/material-source-config/test',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(payload),
        headers: expect.objectContaining({ Authorization: 'Bearer server-token' }),
      }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      'http://backend.test/api/v1/procurement/material-source-config',
      expect.objectContaining({ method: 'PUT', body: JSON.stringify(payload) }),
    )
    expect(mocks.revalidatePath.mock.calls).toEqual([
      ['/purchasing'],
      ['/purchasing/settings'],
    ])
  })
})
