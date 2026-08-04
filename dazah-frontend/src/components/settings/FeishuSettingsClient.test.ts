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

import { buildPayload } from './FeishuSettingsClient'

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
          allowed_group_chat_ids: ['oc_group'],
          require_group_mention: true,
        },
        {
          id: null,
          config_name: 'Livzon 配置',
          app_id: 'old',
          tenant_id: 'old',
          gateway_enabled: true,
          allowed_group_chat_ids: [],
          require_group_mention: true,
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

})
