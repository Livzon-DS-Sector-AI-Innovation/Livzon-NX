import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getAuthHeaders: vi
    .fn()
    .mockResolvedValue({
      Authorization: 'Bearer test-token',
      'Content-Type': 'application/json',
    }),
  revalidatePath: vi.fn(),
}))

vi.mock('@/lib/auth', () => ({ getAuthHeaders: mocks.getAuthHeaders }))
vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))

import * as safety from './safety'

const OH_PAGE_KEY = 'safety:occupational-health-group:oh-monitor'

function jsonResponse(body: unknown, status = 200, headers?: HeadersInit) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json', ...headers },
    }),
  )
}

async function capture(
  fn: () => Promise<unknown>,
): Promise<[string, RequestInit | undefined]> {
  const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: null }))
  vi.stubGlobal('fetch', fetchMock)
  await fn()
  const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
  return [url, init]
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

describe('safety OH 检测报告 actions', () => {
  it('报告列表：查询参数与页面键', async () => {
    const [url] = await capture(() =>
      safety.getOhDetectionReports({ page: 2, page_size: 10, keyword: '噪声', year: 2025 }),
    )
    expect(url).toContain('/api/v1/safety/oh-detection-reports?')
    expect(url).toContain('page=2')
    expect(url).toContain('page_size=10')
    expect(url).toContain('keyword=')
    expect(url).toContain('year=2025')
  })

  it('报告详情', async () => {
    const [url] = await capture(() => safety.getOhDetectionReport('r1'))
    expect(url).toContain('/api/v1/safety/oh-detection-reports/r1')
  })

  it('结果明细：过滤参数与页面键', async () => {
    const [url] = await capture(() =>
      safety.getOhDetectionResults('r1', {
        page: 1,
        factor_category: 'noise',
        record_type: 'point',
        workshop: '合成',
        verdict: 'exceed',
        is_noise_post: true,
        keyword: '甲苯',
      }),
    )
    expect(url).toContain('/api/v1/safety/oh-detection-reports/r1/results?')
    expect(url).toContain('factor_category=noise')
    expect(url).toContain('verdict=exceed')
    expect(url).toContain('is_noise_post=true')
    expect(url).toContain('keyword=')
  })

  it('解析预览：FormData 上传携带页面键', async () => {
    const [url, init] = await capture(() =>
      safety.parseOhDetectionReport(new File(['pdf'], 'r.pdf')),
    )
    expect(url).toContain('/api/v1/safety/oh-detection-reports/parse')
    expect(init?.method).toBe('POST')
    expect((init?.headers as Record<string, string>)['X-Dazah-Page-Key']).toBe(
      OH_PAGE_KEY,
    )
    expect(init?.body).toBeInstanceOf(FormData)
  })

  it('导入：携带表单字段并触发 revalidate', async () => {
    const [url] = await capture(() =>
      safety.importOhDetectionReport(new File(['pdf'], 'r.pdf'), {
        report_no: 'R-2025-01',
        report_name: '年度检测',
      }),
    )
    expect(url).toContain('/api/v1/safety/oh-detection-reports/import')
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/safety/occupational-health')
  })

  it('上传网络失败返回 code -1', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('down'))))
    const res = await safety.parseOhDetectionReport(new File(['pdf'], 'r.pdf'))
    expect(res.code).toBe(-1)
  })

  it('上传后端报错透传 message', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        jsonResponse({ message: '报告编号重复' }, 409),
      ),
    )
    const res = await safety.parseOhDetectionReport(new File(['pdf'], 'r.pdf'))
    expect(res.code).toBe(409)
    expect(res.message).toBe('报告编号重复')
  })

  it('删除报告并触发 revalidate', async () => {
    const [url, init] = await capture(() => safety.deleteOhDetectionReport('r1'))
    expect(url).toContain('/api/v1/safety/oh-detection-reports/r1')
    expect(init?.method).toBe('DELETE')
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/safety/occupational-health')
  })
})

describe('safety 总览未关闭隐患明细 action', () => {
  it('值班镜像源携带值班页面键', async () => {
    const [url, init] = await capture(() =>
      safety.getOpenHazardDetails({ source: 'duty', limit: 5 }),
    )
    expect(url).toContain('/api/v1/safety/open-hazard-details?')
    expect(url).toContain('source=duty')
    expect(url).toContain('limit=5')
    expect((init?.headers as Record<string, string>)['X-Dazah-Page-Key']).toBe(
      'safety:risk-hazard:hazard-inspection:hazard-duty',
    )
  })

  it('台账镜像源携带台账页面键', async () => {
    const [, init] = await capture(() =>
      safety.getOpenHazardDetails({ source: 'ledger' }),
    )
    expect((init?.headers as Record<string, string>)['X-Dazah-Page-Key']).toBe(
      'safety:risk-hazard:hazard-inspection:hazard-quick-report',
    )
  })
})

describe('safety 危化品 MSDS 附件 actions', () => {
  it('附件列表', async () => {
    const [url] = await capture(() => safety.listChemicalMsdsFiles('c1'))
    expect(url).toContain('/api/v1/safety/hazardous-chemicals/c1/msds-files')
  })

  it('删除附件并触发 revalidate', async () => {
    const [url, init] = await capture(() =>
      safety.deleteChemicalMsdsFile('c1', 'f1'),
    )
    expect(url).toContain('/api/v1/safety/hazardous-chemicals/c1/msds-files/f1')
    expect(init?.method).toBe('DELETE')
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/safety/hazchem')
  })

  it('重新提取附件 AI 识别', async () => {
    const [url, init] = await capture(() =>
      safety.reextractChemicalMsdsFile('c1', 'f1'),
    )
    expect(url).toContain('/msds-files/f1/extract')
    expect(init?.method).toBe('POST')
  })

  it('字节读取返回 base64 与 content-type', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(Uint8Array.from([1, 2, 3]), {
            status: 200,
            headers: { 'Content-Type': 'application/pdf' },
          }),
        ),
      ),
    )
    const res = await safety.fetchChemicalMsdsBytes('c1', 'f1', true)
    expect(res.contentType).toBe('application/pdf')
    expect(res.base64.length).toBeGreaterThan(0)
  })

  it('字节读取失败抛错', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => jsonResponse({ message: 'x' }, 500)),
    )
    await expect(
      safety.fetchChemicalMsdsBytes('c1', 'f1', false),
    ).rejects.toThrow('MSDS 读取失败')
  })
})
