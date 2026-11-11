import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getAuthHeaders: vi.fn().mockResolvedValue({ Authorization: 'Bearer test-token' }),
  revalidatePath: vi.fn(),
}))

vi.mock('@/lib/auth', () => ({ getAuthHeaders: mocks.getAuthHeaders }))
vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))

import * as safety from './safety'

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    })
  )
}

function stubFetch(
  response: () => Promise<Response> = () => jsonResponse({ code: 200, data: null })
) {
  const fetchMock = vi.fn(response)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function callOf(fetchMock: ReturnType<typeof vi.fn>, index = 0) {
  return fetchMock.mock.calls[index] as unknown as [string, RequestInit | undefined]
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

describe('应急预案 AI 工作台 actions', () => {
  it('生成任务 POST JSON 并刷新列表页', async () => {
    const fetchMock = stubFetch(() =>
      jsonResponse({ code: 200, data: { job_id: 'job-1', kind: 'generate' } })
    )
    const res = await safety.submitEmergencyPlanGenerate('p1', {
      level: 'company',
      accident_type: 'fire',
      location: '危险品库',
    } as never)
    const [url, init] = callOf(fetchMock)
    expect(url).toContain('/api/v1/safety/emergency-plans/p1/ai/generate')
    expect(init?.method).toBe('POST')
    expect(JSON.parse(init?.body as string)).toMatchObject({ location: '危险品库' })
    expect(res.data).toEqual({ job_id: 'job-1', kind: 'generate' })
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/safety/emergency-mgmt')
  })

  it('保存正文 PUT 携带 base_revision_no 乐观锁', async () => {
    const fetchMock = stubFetch()
    await safety.saveEmergencyPlanContent('p1', { preface: 'x' } as never, 7, '人工编辑')
    const [url, init] = callOf(fetchMock)
    expect(url).toContain('/emergency-plans/p1/content')
    expect(init?.method).toBe('PUT')
    expect(JSON.parse(init?.body as string)).toEqual({
      content: { preface: 'x' },
      base_revision_no: 7,
      summary: '人工编辑',
    })
  })

  it('409 冲突以错误码返回而非抛出', async () => {
    stubFetch(() => jsonResponse({ message: '正文已被其他修改更新' }, 409))
    const res = await safety.saveEmergencyPlanContent('p1', {} as never, 1)
    expect(res.code).toBe(409)
  })

  it('审核/定稿/恢复/读取类接口的 URL 与方法', async () => {
    const fetchMock = stubFetch()
    await safety.submitEmergencyPlanReview('p1')
    await safety.finalizeEmergencyPlan('p1')
    await safety.restoreEmergencyPlanRevision('p1', 3)
    await safety.fetchEmergencyPlanContent('p1')
    await safety.fetchEmergencyPlanChecks('p1')
    await safety.fetchEmergencyPlanRevisions('p1')
    await safety.fetchEmergencyPlanRevision('p1', 2)
    await safety.fetchEmergencyPlanJobStatus('p1')
    await safety.fetchEmergencyPlanChatMessages('p1')
    await safety.fetchEmergencyPlanAiOptions()
    const calls = fetchMock.mock.calls.map(
      (call) => call as unknown as [string, RequestInit | undefined]
    )
    const pairs = calls.map(([url, init]) => [
      init?.method ?? 'GET',
      url.replace(/^.*\/api\/v1\/safety/, ''),
    ])
    expect(pairs).toEqual([
      ['POST', '/emergency-plans/p1/ai/review'],
      ['POST', '/emergency-plans/p1/finalize'],
      ['POST', '/emergency-plans/p1/revisions/3/restore'],
      ['GET', '/emergency-plans/p1/content'],
      ['GET', '/emergency-plans/p1/content/checks'],
      ['GET', '/emergency-plans/p1/revisions'],
      ['GET', '/emergency-plans/p1/revisions/2'],
      ['GET', '/emergency-plans/p1/ai/job'],
      ['GET', '/emergency-plans/p1/ai/messages'],
      ['GET', '/emergency-plans/ai/options'],
    ])
    // 选项接口显式带页面权限头
    const optionsInit = calls[calls.length - 1][1]
    expect(
      (optionsInit?.headers as Record<string, string>)['X-Dazah-Page-Key']
    ).toBe('safety:emergency-accident:emergency-mgmt')
  })

  it('导入 docx 以 multipart 上传', async () => {
    const fetchMock = stubFetch()
    const res = await safety.importEmergencyPlanDocx(
      'p1',
      new File(['x'], '预案.docx')
    )
    const [url, init] = callOf(fetchMock)
    expect(url).toContain('/emergency-plans/p1/ai/import')
    expect(init?.method).toBe('POST')
    expect(init?.body).toBeInstanceOf(FormData)
    expect(res.code).toBe(200)
  })

  it('导出 Word 返回 base64 与 UTF-8 文件名', async () => {
    stubFetch(() =>
      Promise.resolve(
        new Response(new Uint8Array([100, 97, 116, 97]), {
          status: 200,
          headers: {
            'content-disposition': `attachment; filename*=utf-8''${encodeURIComponent('预案(公司级).docx')}`,
          },
        })
      )
    )
    const result = await safety.fetchEmergencyPlanDocxBytes('p1')
    expect(result.base64).toBe('ZGF0YQ==')
    expect(result.fileName).toBe('预案(公司级).docx')
  })

  it('导出失败抛出带状态码的错误', async () => {
    stubFetch(() => Promise.resolve(new Response('无正文', { status: 422 })))
    await expect(safety.fetchEmergencyPlanDocxBytes('p1')).rejects.toThrow('422')
  })

  it('预案附件下载返回 base64（不再在服务端操作 DOM）', async () => {
    stubFetch(() =>
      Promise.resolve(
        new Response(new Uint8Array([120]), {
          status: 200,
          headers: { 'content-disposition': 'attachment; filename="plan.pdf"' },
        })
      )
    )
    const result = await safety.fetchEmergencyPlanFileBytes('p1')
    expect(result).toEqual({ base64: 'eA==', fileName: 'plan.pdf' })
  })
})
