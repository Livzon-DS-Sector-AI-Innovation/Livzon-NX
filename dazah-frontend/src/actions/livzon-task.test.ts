import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getAuthHeaders: vi.fn().mockResolvedValue({
    'Content-Type': 'application/json',
  }),
}))

vi.mock('@/lib/auth', () => ({ getAuthHeaders: mocks.getAuthHeaders }))
vi.mock('@/lib/server-api', () => ({
  getServerApiBaseUrl: () => 'http://backend.test',
}))

import {
  executeLivzonTaskConfirmation,
  requestLivzonTaskTool,
} from './livzon-task'

describe('Livzon task actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('sends tool requests through the Agent control endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          data: { ok: true, operation: 'quality.list_deviations' },
        }),
        { status: 200 },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await requestLivzonTaskTool({
      operation: 'quality.list_deviations',
      params: {},
    })

    expect(result).toEqual({
      ok: true,
      operation: 'quality.list_deviations',
    })
    expect(fetchMock).toHaveBeenCalledWith(
      'http://backend.test/api/v1/agent/control/tools/execute',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          operation: 'quality.list_deviations',
          params: {},
        }),
      }),
    )
  })

  it('surfaces confirmation API error messages', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ message: '确认项已过期' }), {
          status: 410,
        }),
      ),
    )

    await expect(
      executeLivzonTaskConfirmation('confirmation-1'),
    ).rejects.toThrow('确认项已过期')
  })
})
