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
  exportAgentTrace,
  getAgentCapabilityImpacts,
  getAgentConfirmations,
  getAgentDeliveries,
  getAgentOperationsHealth,
  getAgentRuntimeOverview,
  getAgentToolCatalogPage,
  getAgentTrace,
  getExternalIdentityBindings,
  getExternalIdentityConflicts,
  getFeishuAuthorizations,
  getLivzonFeishuGatewayStatus,
  restartLivzonFeishuGateway,
  revokeFeishuAuthorization,
  setAgentToolEnabled,
  syncLivzonFeishuDirectory,
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
      tenantId: 'tenant/a',
      status: 'suspended',
      department: '质量部',
      activeSince: '2026-08-01T00:00:00Z',
    })

    expect(fetchMock).toHaveBeenCalledWith(
      'http://backend.test/api/v1/identity/external-identity-bindings?page=2&page_size=25&keyword=%E5%BC%A0+%E4%B8%89&tenant_id=tenant%2Fa&status_value=suspended&department=%E8%B4%A8%E9%87%8F%E9%83%A8&active_since=2026-08-01T00%3A00%3A00Z',
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

  it('restarts the Hermes gateway through the protected backend action', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          data: {
            status: 'connected',
            message: '已恢复',
            previous_reconnects: 1,
            gateway_reconnects: 2,
            credential_version: 3,
            config_version: 3,
          },
        }),
        { status: 200 },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(restartLivzonFeishuGateway()).resolves.toEqual(
      expect.objectContaining({ status: 'connected', gateway_reconnects: 2 }),
    )
    expect(fetchMock).toHaveBeenCalledWith(
      'http://backend.test/api/v1/identity/feishu-config/gateway/restart',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('covers identity synchronization and conflict endpoints', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: [] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: {
        status: 'ok', message: '同步完成', bindings: { created: 1, existing: 0, conflicts: [] },
      } }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(getExternalIdentityConflicts()).resolves.toEqual([])
    await expect(syncLivzonFeishuDirectory()).resolves.toEqual(
      expect.objectContaining({ status: 'ok' }),
    )
    expect(fetchMock).toHaveBeenLastCalledWith(
      'http://backend.test/api/v1/identity/sync/all',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('serializes every tool catalog filter', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ data: { items: [], page: 3, page_size: 10, total: 0 } }), { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await getAgentToolCatalogPage({
      page: 3,
      pageSize: 10,
      keyword: '偏差',
      module: 'quality',
      status: 'active',
      riskLevel: 'high',
      write: false,
    })

    expect(fetchMock).toHaveBeenCalledWith(
      'http://backend.test/api/v1/agent/control/tools/page?page=3&page_size=10&keyword=%E5%81%8F%E5%B7%AE&module=quality&status_value=active&risk_level=high&write=false',
      expect.any(Object),
    )
  })

  it('manages remembered Feishu authorizations', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: { items: [{ id: 'grant-1' }] } }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: { id: 'grant/1', status: 'revoked' } }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(getFeishuAuthorizations('user/a')).resolves.toEqual([{ id: 'grant-1' }])
    await expect(revokeFeishuAuthorization('grant/1', 'user/a')).resolves.toEqual(
      { id: 'grant/1', status: 'revoked' },
    )
    expect(fetchMock).toHaveBeenLastCalledWith(
      'http://backend.test/api/v1/identity/feishu-config/authorizations/grant%2F1?user_id=user%2Fa',
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('loads confirmation, delivery, runtime, health and impact governance data', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: { items: [], page: 2, page_size: 5, total: 0 } }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: { pending_confirmations: 1 } }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: { items: [] } }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: { status: 'healthy' } }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: [] }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await getAgentConfirmations({ page: 2, pageSize: 5, status: 'pending', userId: 'user/a' })
    await getAgentRuntimeOverview()
    await getAgentDeliveries('failed')
    await getAgentOperationsHealth()
    await getAgentCapabilityImpacts()

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      'http://backend.test/api/v1/agent/control/confirmations?page=2&page_size=5&status_value=pending&user_id=user%2Fa',
      'http://backend.test/api/v1/agent/control/runtime-overview',
      'http://backend.test/api/v1/agent/push-deliveries?page=1&page_size=50&status_value=failed',
      'http://backend.test/api/v1/agent/operations/health',
      'http://backend.test/api/v1/agent/automation-capability-impacts',
    ])
  })

  it('exports a trace as text and reports HTTP failures', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response('{"safe":true}', { status: 200 }))
      .mockResolvedValueOnce(new Response('', { status: 503 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(exportAgentTrace('trace/a')).resolves.toEqual({
      filename: 'livzon-trace-trace/a.json',
      content: '{"safe":true}',
    })
    await expect(exportAgentTrace('trace/a')).rejects.toThrow('Trace 导出失败 (503)')
    expect(fetchMock).toHaveBeenCalledWith(
      'http://backend.test/api/v1/agent/control/traces/trace%2Fa/export',
      expect.objectContaining({ cache: 'no-store' }),
    )
  })
})
