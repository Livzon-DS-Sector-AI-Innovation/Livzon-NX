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
  getLivzonFeishuGatewayStatus,
  setAgentToolEnabled,
} from './settings'

describe('settings Agent and Feishu actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('unwraps the Hermes gateway status envelope', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            data: {
              configured: true,
              credential_version: 4,
              config_version: 7,
              tenant_id: 'tenant-a',
              gateway_enabled: true,
              gateway: 'connected',
              gateway_reconnects: 1,
            },
          }),
          { status: 200 },
        ),
      ),
    )

    await expect(getLivzonFeishuGatewayStatus()).resolves.toEqual(
      expect.objectContaining({
        gateway: 'connected',
        config_version: 7,
      }),
    )
  })

  it('encodes tool operations when changing catalog state', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          data: {
            operation: 'quality.create_deviation',
            status: 'disabled',
          },
        }),
        { status: 200 },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    await setAgentToolEnabled('quality.create_deviation', false)

    expect(fetchMock).toHaveBeenCalledWith(
      'http://backend.test/api/v1/agent/tools/quality.create_deviation/enabled',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ enabled: false }),
      }),
    )
  })
})
