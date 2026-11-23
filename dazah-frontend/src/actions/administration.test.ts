import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  cookies: vi.fn().mockResolvedValue({
    get: vi.fn().mockReturnValue({ value: 'admin-action-token' }),
  }),
  revalidatePath: vi.fn(),
}))

vi.mock('next/headers', () => ({
  cookies: mocks.cookies,
  headers: vi.fn(async () => new Headers({ 'X-Dazah-Page-Path': '/admin/settings/feishu' })),
}))
vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))

import {
  createAdministrationFeishuRootAction,
  deleteAdministrationFeishuRootAction,
  discoverAdministrationFeishuRootAction,
  generateTobaccoGiftAiAnalysisAction,
  importNoticeAction,
  parseNoticeAction,
  saveAdministrationFeishuConfigAction,
  saveAdministrationPageBindingsAction,
  syncAdministrationFeishuResourceAction,
  syncAdministrationFeishuResourcesAction,
  testAdministrationFeishuConfigAction,
} from './administration'

function response(data: unknown = { ok: true }, status = 200): Response {
  return new Response(JSON.stringify({ code: status, message: status === 200 ? 'ok' : '凭据未配置', data }), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

const config = {
  config_name: '行政飞书',
  app_id: 'cli_test',
  app_secret: 'secret',
  is_active: true,
  timezone: 'Asia/Shanghai',
  daily_sync_time: '02:00',
  remark: null,
}

describe('administration server actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('forwards settings writes with the Feishu settings page context', async () => {
    const fetchMock = vi.fn().mockImplementation(async () => response({ app_id: 'cli_test' }))
    vi.stubGlobal('fetch', fetchMock)

    const saved = await saveAdministrationFeishuConfigAction(config)
    expect(saved).toEqual({ app_id: 'cli_test' })
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toMatch(/\/api\/v1\/administration\/feishu-config$/)
    expect(init.method).toBe('PUT')
    expect(init.headers['X-Dazah-Page-Key']).toBe('admin:feishu-settings')
    expect(init.headers.Authorization).toBe('Bearer admin-action-token')
    expect(JSON.parse(init.body)).toMatchObject({ app_id: 'cli_test' })
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/admin/settings/feishu')

    await testAdministrationFeishuConfigAction(config)
    expect(String(fetchMock.mock.calls[1][0])).toMatch(/feishu-config\/test$/)
    expect(fetchMock.mock.calls[1][1].method).toBe('POST')
  })

  it('maintains roots, syncs resources sequentially and saves bindings', async () => {
    const fetchMock = vi.fn().mockImplementation(async () => response())
    vi.stubGlobal('fetch', fetchMock)

    await createAdministrationFeishuRootAction({
      name: '烟酒礼品',
      source_type: 'base',
      source_url: 'https://example.feishu.cn/base/abc',
    })
    await deleteAdministrationFeishuRootAction('root/1')
    await discoverAdministrationFeishuRootAction('root-2')
    await syncAdministrationFeishuResourceAction('res-1')
    await syncAdministrationFeishuResourcesAction(['res-2', 'res-3'])
    await saveAdministrationPageBindingsAction('admin:tobacco-gift:items', [
      {
        resource_id: 'res-1',
        tab_name: '物品清单',
        sort_order: 0,
        is_default: true,
        is_enabled: true,
        visible_field_ids: [],
      },
    ])

    const calls = fetchMock.mock.calls.map(([url, init]) => `${init.method} ${String(url)}`)
    expect(calls[0]).toMatch(/^POST .*\/administration\/feishu-read\/roots$/)
    expect(calls[1]).toMatch(/^DELETE .*\/feishu-read\/roots\/root%2F1$/)
    expect(calls[2]).toMatch(/^POST .*\/feishu-read\/roots\/root-2\/discover$/)
    expect(calls[3]).toMatch(/^POST .*\/feishu-read\/resources\/res-1\/sync$/)
    expect(calls[4]).toMatch(/resources\/res-2\/sync$/)
    expect(calls[5]).toMatch(/resources\/res-3\/sync$/)
    expect(calls[6]).toMatch(
      /^PUT .*\/feishu-read\/page-bindings\/admin%3Atobacco-gift%3Aitems$/,
    )
    expect(JSON.parse(fetchMock.mock.calls[6][1].body).bindings).toHaveLength(1)
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/admin/tobacco-gift', 'layout')
  })

  it('surfaces backend error messages', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(null, 400)))
    await expect(saveAdministrationFeishuConfigAction(config)).rejects.toThrow('凭据未配置')
  })

  it('falls back to status text when error body is not JSON', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('gateway down', { status: 502 })),
    )
    await expect(discoverAdministrationFeishuRootAction('root-1')).rejects.toThrow('请求失败（502）')
  })
})

describe('generateTobaccoGiftAiAnalysisAction', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('posts to the ai-analysis endpoint with the dashboard page context', async () => {
    const fetchMock = vi.fn().mockImplementation(async () =>
      response({ summary: '概述', insights: [], anomalies: [], suggestions: [], generated_at: '2026-11-23T08:00:00Z' }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await generateTobaccoGiftAiAnalysisAction()
    expect(result).toEqual({
      ok: true,
      data: {
        summary: '概述',
        insights: [],
        anomalies: [],
        suggestions: [],
        generated_at: '2026-11-23T08:00:00Z',
      },
    })
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toMatch(/\/api\/v1\/administration\/tobacco-gift\/ai-analysis$/)
    expect(init.method).toBe('POST')
    expect(init.headers['X-Dazah-Page-Key']).toBe('admin:tobacco-gift:dashboard')
  })

  it('propagates backend messages as user-facing errors', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => response(null, 503)))
    const result = await generateTobaccoGiftAiAnalysisAction()
    expect(result).toEqual({ ok: false, message: '凭据未配置' })
  })
})

describe('notice upload actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('forwards multipart parse with the notice page context', async () => {
    const fetchMock = vi.fn().mockImplementation(async () =>
      response({ file_name: '公告.docx', suggestion: { notice_no: '2026-001' } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const file = new File(['公告内容'], '公告.docx', { type: 'application/msword' })
    const result = await parseNoticeAction(file)

    expect(result).toEqual({
      code: 200,
      data: { file_name: '公告.docx', suggestion: { notice_no: '2026-001' } },
    })
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toMatch(/\/api\/v1\/administration\/notices\/parse$/)
    expect(init.method).toBe('POST')
    expect(init.headers['X-Dazah-Page-Key']).toBe('admin:notice')
    // multipart 转发必须剥离自动 Content-Type（让浏览器带 boundary）
    expect(init.headers['Content-Type']).toBeUndefined()
    expect(init.body).toBeInstanceOf(FormData)
    expect(init.body.get('file').name).toBe('公告.docx')
    expect(mocks.revalidatePath).not.toHaveBeenCalled()
  })

  it('forwards confirmed fields on import and revalidates the ledger', async () => {
    const fetchMock = vi.fn().mockImplementation(async () =>
      response({ id: 'n-1', notice_no: '2026-001', title: '培训通知' }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const file = new File(['公告内容'], '公告.docx', { type: 'application/msword' })
    const result = await importNoticeAction(file, {
      notice_no: '2026-001',
      title: '培训通知',
      publisher: '安全环保部',
      published_at: '2026-03-05',
      category: '安全公告',
      remark: '',
    })

    expect(result.code).toBe(200)
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toMatch(/\/api\/v1\/administration\/notices$/)
    expect(init.body.get('notice_no')).toBe('2026-001')
    expect(init.body.get('title')).toBe('培训通知')
    // 空串字段不追加（后端按缺省处理）
    expect(init.body.get('remark')).toBeNull()
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/admin/notice')
  })

  it('maps backend failures to status-coded envelopes', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async () =>
        new Response(
          JSON.stringify({ detail: 'AI 模型服务暂不可用，请稍后重试识别' }),
          { status: 502, headers: { 'content-type': 'application/json' } },
        ),
      ),
    )
    const result = await parseNoticeAction(new File(['x'], '公告.docx'))
    expect(result.code).toBe(502)
    expect(result.message).toContain('暂不可用')
    expect(result.data).toBeUndefined()
  })
})
