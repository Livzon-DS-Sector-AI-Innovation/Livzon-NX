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
  getAgentTrace,
  getExternalIdentityBindings,
  getLivzonFeishuGatewayStatus,
  setAgentToolEnabled,
  updateExternalIdentityBindingStatus,
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

  it('uses server-side paging and filters for identity governance', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          data: { items: [], page: 2, page_size: 25, total: 0 },
        }),
        { status: 200 },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    await getExternalIdentityBindings({
      page: 2,
      pageSize: 25,
      keyword: '张 三',
      status: 'suspended',
    })

    expect(fetchMock).toHaveBeenCalledWith(
      'http://backend.test/api/v1/identity/external-identity-bindings?page=2&page_size=25&keyword=%E5%BC%A0+%E4%B8%89&status_value=suspended',
      expect.any(Object),
    )
  })

  it('records explicit identity lifecycle transitions', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ data: { status: 'revoked' } }), {
        status: 200,
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await updateExternalIdentityBindingStatus('binding/a', 'revoked')

    expect(fetchMock).toHaveBeenCalledWith(
      'http://backend.test/api/v1/identity/external-identity-bindings/binding%2Fa/status',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ status: 'revoked' }),
      }),
    )
  })

  it('encodes trace identifiers and keeps diagnostics server-side', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ data: { trace_id: 'trace/a', timeline: [] } }),
        { status: 200 },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    await getAgentTrace('trace/a')

    expect(fetchMock).toHaveBeenCalledWith(
      'http://backend.test/api/v1/agent/control/traces/trace%2Fa',
      expect.any(Object),
    )
  })
})
