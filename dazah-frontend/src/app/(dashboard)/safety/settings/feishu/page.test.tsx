import { renderToStaticMarkup } from 'react-dom/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getSafetyFeishuSettings: vi.fn(),
  getSafetyFeishuWsStatus: vi.fn(),
  FeishuSettingsPage: vi.fn((_props: Record<string, unknown>) => null),
}))

vi.mock('@/actions/safety', () => ({
  getSafetyFeishuSettings: mocks.getSafetyFeishuSettings,
  getSafetyFeishuWsStatus: mocks.getSafetyFeishuWsStatus,
}))

vi.mock('@/components/safety', () => ({ FeishuSettingsPage: mocks.FeishuSettingsPage }))

import SafetyFeishuSettingsRoutePage, { dynamic } from './page'

describe('safety feishu settings route page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('loads settings and websocket status, then passes them to the client page', async () => {
    const settings = { app_id: 'cli_safety', is_enabled: true }
    const wsStatus = { connected: true }
    mocks.getSafetyFeishuSettings.mockResolvedValueOnce({ code: 200, data: settings })
    mocks.getSafetyFeishuWsStatus.mockResolvedValueOnce({ code: 200, data: wsStatus })

    const element = await SafetyFeishuSettingsRoutePage()
    const markup = renderToStaticMarkup(element as never)

    expect(mocks.getSafetyFeishuSettings).toHaveBeenCalled()
    expect(mocks.getSafetyFeishuWsStatus).toHaveBeenCalled()
    expect(mocks.FeishuSettingsPage.mock.calls.at(-1)?.[0]).toMatchObject({
      initialSettings: settings,
      initialWsStatus: wsStatus,
    })
    expect(markup).toContain('飞书设置')
    expect(dynamic).toBe('force-dynamic')
  })

  it('falls back to null when the backend returns no payload', async () => {
    mocks.getSafetyFeishuSettings.mockResolvedValueOnce({ code: 200, data: null })
    mocks.getSafetyFeishuWsStatus.mockResolvedValueOnce({ code: 500, message: '不可用' })

    const element = await SafetyFeishuSettingsRoutePage()
    renderToStaticMarkup(element as never)

    expect(mocks.FeishuSettingsPage.mock.calls.at(-1)?.[0]).toMatchObject({
      initialSettings: null,
      initialWsStatus: null,
    })
  })
})