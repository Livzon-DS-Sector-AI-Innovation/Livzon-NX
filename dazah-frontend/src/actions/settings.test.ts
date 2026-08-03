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
  createExternalIdentityBinding,
  disableExternalIdentityBinding,
  getAgentToolCatalog,
  getExternalIdentityBindings,
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

  it('uses the external identity binding endpoints and payloads', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ data: [{ id: 'binding-1' }] }), {
          status: 200,
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ data: { id: 'binding-2' } }), {
          status: 200,
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ data: { id: 'binding-2', status: 'disabled' } }),
          { status: 200 },
        ),
      )
    vi.stubGlobal('fetch', fetchMock)

    await expect(getExternalIdentityBindings()).resolves.toEqual([
      { id: 'binding-1' },
    ])
    const payload = {
      tenant_id: 'tenant-a',
      platform: 'feishu' as const,
      app_fingerprint: 'cli_app',
      external_open_id: 'ou_user',
      local_user_id: '00000000-0000-0000-0000-000000000001',
    }
    await createExternalIdentityBinding(payload)
    await disableExternalIdentityBinding('binding-2')

    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      'http://backend.test/api/v1/identity/external-identity-bindings',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      'http://backend.test/api/v1/identity/external-identity-bindings/binding-2/disable',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('loads the discovered Agent tool catalog', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            data: [{ operation: 'quality.create_deviation', status: 'active' }],
          }),
          { status: 200 },
        ),
      ),
    )

    await expect(getAgentToolCatalog()).resolves.toEqual([
      { operation: 'quality.create_deviation', status: 'active' },
    ])
  })
})
