import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getAuthHeaders: vi.fn().mockResolvedValue({ Authorization: 'Bearer test-token' }),
  revalidatePath: vi.fn(),
}))

vi.mock('@/lib/auth', () => ({ getAuthHeaders: mocks.getAuthHeaders }))
vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))

import {
  createCheck,
  deleteKnowledgeAttachment,
  fetchHazardStats,
  getChecks,
  getHazard,
  getKnowledgeArticles,
  getSafetyFeishuSettings,
  getSafetyFeishuWsStatus,
  restartSafetyFeishuWs,
  saveSafetyFeishuSettings,
  submitCheck,
  syncSafetyKnowledge,
  testSafetyFeishuSettings,
  uploadKnowledgeAttachments,
} from './safety'

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('safety actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('lists safety checks with query params', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { items: [], total: 0 } }))
    vi.stubGlobal('fetch', fetchMock)

    await getChecks({ page: 1, page_size: 20, status: 'pending' })
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/safety/checks?'),
      expect.anything(),
    )
  })

  it('creates a safety check', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { id: 'ck-1' } }))
    vi.stubGlobal('fetch', fetchMock)

    const payload = { check_type: '日常巡检', location: '102车间' }
    await createCheck(payload as never)
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/safety/checks`,
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('submits a check', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: null }))
    vi.stubGlobal('fetch', fetchMock)

    await submitCheck('ck-1')
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/safety/checks/ck-1/submit`,
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('fetches hazard stats', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { total: 5 } }))
    vi.stubGlobal('fetch', fetchMock)

    const res = await fetchHazardStats()
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/safety/hazards/stats'),
      expect.anything(),
    )
    expect(res).toMatchObject({ code: 200 })
  })

  it('fetches a single hazard', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { id: 'hz-1' } }))
    vi.stubGlobal('fetch', fetchMock)

    await getHazard('hz-1')
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/safety/hazards/hz-1`,
      expect.anything(),
    )
  })
})

const KNOWLEDGE_PAGE_KEY = 'safety:regulation-info:knowledge-base'
const SETTINGS_PAGE_KEY = 'safety:system-config:safety-feishu-settings'

describe('safety knowledge actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('lists knowledge articles with regulation status and keyword filters', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: [], meta: { total: 0 } }))
    vi.stubGlobal('fetch', fetchMock)

    await getKnowledgeArticles({
      page: 2,
      page_size: 20,
      regulation_status: '现行有效',
      keyword: '安全',
    })
    const [url] = fetchMock.mock.calls[0] as unknown as [string]
    expect(url).toContain('/api/v1/safety/knowledge-articles?')
    expect(url).toContain('regulation_status=%E7%8E%B0%E8%A1%8C%E6%9C%89%E6%95%88')
    expect(url).toContain('keyword=%E5%AE%89%E5%85%A8')
  })

  it('skips the request when no attachment files are provided', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: null }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(uploadKnowledgeAttachments('doc-1', [])).resolves.toEqual({
      code: 200,
      data: null,
    })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('uploads attachments as multipart without a JSON content type', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { id: 'doc-1' } }))
    vi.stubGlobal('fetch', fetchMock)

    const file = new File(['abc'], 'sop.pdf', { type: 'application/pdf' })
    await uploadKnowledgeAttachments('doc-1', [file])

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe(`${API_BASE}/api/v1/safety/knowledge-articles/doc-1/attachments`)
    expect(init.method).toBe('POST')
    expect(init.body).toBeInstanceOf(FormData)
    const headers = init.headers as Record<string, string>
    expect(headers['X-Dazah-Page-Key']).toBe(KNOWLEDGE_PAGE_KEY)
    expect(headers.Authorization).toBe('Bearer test-token')
    expect(headers['Content-Type']).toBeUndefined()
  })

  it('deletes a local attachment with the knowledge page key', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { id: 'doc-1' } }))
    vi.stubGlobal('fetch', fetchMock)

    await deleteKnowledgeAttachment('doc-1', 'tok-1')
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/safety/knowledge-articles/doc-1/attachments/tok-1`,
      expect.objectContaining({
        method: 'DELETE',
        headers: expect.objectContaining({ 'X-Dazah-Page-Key': KNOWLEDGE_PAGE_KEY }),
      }),
    )
  })

  it('syncs the feishu regulation mirror', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { created: 1 } }))
    vi.stubGlobal('fetch', fetchMock)

    await syncSafetyKnowledge()
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/safety/knowledge-articles/feishu/sync`,
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ 'X-Dazah-Page-Key': KNOWLEDGE_PAGE_KEY }),
      }),
    )
  })
})

describe('safety feishu settings actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('loads the app settings with the settings page key', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { app_id: 'cli_x' } }))
    vi.stubGlobal('fetch', fetchMock)

    const res = await getSafetyFeishuSettings()
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/safety/feishu-settings/app`,
      expect.objectContaining({
        headers: expect.objectContaining({ 'X-Dazah-Page-Key': SETTINGS_PAGE_KEY }),
      }),
    )
    expect(res).toMatchObject({ code: 200 })
  })

  it('saves the app settings as JSON', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { app_id: 'cli_x' } }))
    vi.stubGlobal('fetch', fetchMock)

    const payload = { app_id: 'cli_x', app_secret: 'secret', is_enabled: true }
    await saveSafetyFeishuSettings(payload)
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/safety/feishu-settings/app`,
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify(payload),
        headers: expect.objectContaining({ 'X-Dazah-Page-Key': SETTINGS_PAGE_KEY }),
      }),
    )
  })

  it('tests the app credentials', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { success: true } }))
    vi.stubGlobal('fetch', fetchMock)

    await testSafetyFeishuSettings()
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/safety/feishu-settings/app/test`,
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ 'X-Dazah-Page-Key': SETTINGS_PAGE_KEY }),
      }),
    )
  })

  it('reads and restarts the feishu websocket subscription', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { connected: true } }))
    vi.stubGlobal('fetch', fetchMock)

    await getSafetyFeishuWsStatus()
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/safety/feishu/ws/status`,
      expect.anything(),
    )

    await restartSafetyFeishuWs()
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/safety/feishu/ws/restart`,
      expect.objectContaining({ method: 'POST' }),
    )
  })
})
