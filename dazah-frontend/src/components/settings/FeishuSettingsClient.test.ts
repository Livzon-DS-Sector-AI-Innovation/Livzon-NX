import { afterEach, describe, expect, it, vi } from 'vitest'

const actionMocks = vi.hoisted(() => ({
  createExternalIdentityBinding: vi.fn(),
  disableExternalIdentityBinding: vi.fn(),
  getAgentToolCatalog: vi.fn(),
  getExternalIdentityBindings: vi.fn(),
  getLivzonFeishuConfig: vi.fn(),
  getLivzonFeishuGatewayStatus: vi.fn(),
  setAgentToolEnabled: vi.fn(),
}))

vi.mock('@/actions/settings', () => actionMocks)

import {
  buildPayload,
  requestFeishuConfig,
} from './FeishuSettingsClient'

describe('Feishu settings request contracts', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('builds a normalized Gateway credential payload', () => {
    expect(
      buildPayload(
        {
          app_id: ' cli_app ',
          app_secret: ' secret ',
          tenant_id: ' tenant-a ',
          gateway_enabled: false,
        },
        {
          id: null,
          config_name: 'Livzon 配置',
          app_id: 'old',
          tenant_id: 'old',
          gateway_enabled: true,
          config_version: 1,
          app_secret_configured: true,
          app_secret_masked: '***',
          is_active: true,
        },
      ),
    ).toEqual(
      expect.objectContaining({
        config_name: 'Livzon 配置',
        app_id: 'cli_app',
        app_secret: 'secret',
        tenant_id: 'tenant-a',
        gateway_enabled: false,
        is_active: true,
      }),
    )
  })

  it('unwraps successful responses and sends same-origin JSON', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ data: { gateway_enabled: true } }), {
        status: 200,
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(
      requestFeishuConfig<{ gateway_enabled: boolean }>(
        '/test',
        {
          app_id: 'cli_app',
          tenant_id: 'tenant-a',
          gateway_enabled: true,
          is_active: true,
          config_name: 'Livzon',
        },
        'POST',
      ),
    ).resolves.toEqual({ gateway_enabled: true })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/identity/feishu-config/test',
      expect.objectContaining({
        method: 'POST',
        credentials: 'same-origin',
      }),
    )
  })

  it('maps API and malformed-envelope failures', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: '凭证无效' }), { status: 403 }),
      ).mockResolvedValueOnce(
        new Response(JSON.stringify({ message: 'missing data' }), {
          status: 200,
        }),
      ),
    )
    const payload = {
      app_id: 'cli_app',
      tenant_id: 'tenant-a',
      gateway_enabled: true,
      is_active: true,
      config_name: 'Livzon',
    }

    await expect(requestFeishuConfig('', payload, 'PUT')).rejects.toThrow(
      '凭证无效',
    )
    await expect(requestFeishuConfig('', payload, 'PUT')).rejects.toThrow(
      '返回格式无效',
    )
  })
})
