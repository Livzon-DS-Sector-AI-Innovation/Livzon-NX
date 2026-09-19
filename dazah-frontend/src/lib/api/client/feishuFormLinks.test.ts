import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchOnboardingFormUrl } from './hr'
import {
  fetchWarehouseHomeQuickFormLinks,
  fetchWarehousePageFormLinks,
} from './warehouse'

const fetchMock = vi.fn()

afterEach(() => {
  vi.restoreAllMocks()
  fetchMock.mockReset()
})

function jsonResponse(payload: unknown, ok = true, status = 200) {
  return {
    ok,
    status,
    json: async () => payload,
  } as Response
}

describe('feishu form-link client helpers', () => {
  it('fetchOnboardingFormUrl returns configured form url', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ code: 200, data: { form_url: 'https://www.feishu.cn/share/base/form/shrcn_x' } })
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchOnboardingFormUrl()).resolves.toBe(
      'https://www.feishu.cn/share/base/form/shrcn_x'
    )
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/hr/onboarding-records/form-url', {
      cache: 'no-store',
    })
  })

  it('fetchOnboardingFormUrl returns null when unconfigured or request fails', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ code: 200, data: { form_url: null } })
    )
    vi.stubGlobal('fetch', fetchMock)
    await expect(fetchOnboardingFormUrl()).resolves.toBeNull()

    fetchMock.mockResolvedValue(jsonResponse({}, false, 503))
    await expect(fetchOnboardingFormUrl()).resolves.toBeNull()
  })

  it('fetchWarehousePageFormLinks returns inbound/outbound links for the page', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        code: 200,
        data: {
          inbound_form_url: 'https://www.feishu.cn/share/base/form/shrcn_in',
          outbound_form_url: null,
        },
      })
    )
    vi.stubGlobal('fetch', fetchMock)

    const links = await fetchWarehousePageFormLinks('inbound-ledger')
    expect(links.inbound_form_url).toContain('shrcn_in')
    expect(links.outbound_form_url).toBeNull()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/warehouse/material-pages/inbound-ledger/form-links',
      { cache: 'no-store' }
    )
  })

  it('fetchWarehousePageFormLinks throws when the endpoint fails', async () => {
    fetchMock.mockResolvedValue(jsonResponse({}, false, 400))
    vi.stubGlobal('fetch', fetchMock)
    await expect(fetchWarehousePageFormLinks('raw-summary')).rejects.toThrow('获取表单链接失败')
  })

  it('fetchWarehouseHomeQuickFormLinks sends the inbound-ledger page context', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        code: 200,
        data: {
          'inbound-ledger': {
            inbound_form_url: 'https://www.feishu.cn/share/base/form/shrcn_home',
            outbound_form_url: null,
          },
        },
      })
    )
    vi.stubGlobal('fetch', fetchMock)

    const links = await fetchWarehouseHomeQuickFormLinks()
    expect(links['inbound-ledger']?.inbound_form_url).toContain('shrcn_home')
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/warehouse/home-quick-form-links')
    expect((init as { headers: Record<string, string> }).headers['X-Dazah-Page-Key']).toBe(
      'warehouse:materials:inbound-ledger'
    )
  })
})
