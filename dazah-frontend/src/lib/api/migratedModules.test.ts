/* @vitest-environment happy-dom */

import { beforeEach, describe, expect, it, vi } from 'vitest'

import * as adminApi from '@/lib/api/client/admin'
import * as hrApi from '@/lib/api/client/hr'
import * as qualityClientApi from '@/lib/api/client/quality'
import * as registrationClientApi from '@/lib/api/client/registration'
import * as regulatoryTrackerClientApi from '@/lib/api/client/regulatoryTracker'
import * as warehouseClientApi from '@/lib/api/client/warehouse'
import * as qualityExternalApi from '@/lib/api/quality-external'
import * as qualityOosOotApi from '@/lib/api/quality-oos-oot'
import * as registrationApi from '@/lib/api/registration'

type AsyncApi = (...args: unknown[]) => Promise<unknown>

function successfulResponse(): Response {
  const body = {
    code: 200,
    message: 'ok',
    data: [],
    items: [],
    meta: { total: 0, page: 1, page_size: 20 },
    total: 0,
  }
  return {
    ok: true,
    status: 200,
    statusText: 'OK',
    headers: new Headers({ 'content-disposition': 'attachment; filename=test.docx' }),
    json: vi.fn().mockResolvedValue(body),
    text: vi.fn().mockResolvedValue('test'),
    blob: vi.fn().mockResolvedValue(new Blob(['test'])),
    arrayBuffer: vi.fn().mockResolvedValue(new ArrayBuffer(0)),
  } as unknown as Response
}

function selectApis(
  module: Record<string, unknown>,
  pattern: RegExp,
): Array<[string, AsyncApi]> {
  return Object.entries(module).filter(
    (entry): entry is [string, AsyncApi] =>
      pattern.test(entry[0]) && typeof entry[1] === 'function',
  )
}

async function invokeApis(entries: Array<[string, AsyncApi]>): Promise<void> {
  for (const [, api] of entries) {
    const args = Array.from({ length: api.length }, () => 'demo')
    await api(...args)
  }
}

describe('migrated module browser API contracts', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => successfulResponse()))
  })

  it('constructs all migrated HR read requests through the application proxy', async () => {
    const apis = selectApis(hrApi, /^(fetch|search)/)

    expect(apis.length).toBeGreaterThanOrEqual(55)
    await invokeApis(apis)

    const fetchMock = vi.mocked(fetch)
    expect(fetchMock).toHaveBeenCalledTimes(apis.length)
    expect(fetchMock.mock.calls.every(([url]) => String(url).startsWith('/api/v1/hr/'))).toBe(true)
  })

  it('constructs quality, registration, and system permission read requests', async () => {
    const apis = [
      ...selectApis(qualityExternalApi, /^fetch/),
      ...selectApis(qualityOosOotApi, /^fetch/),
      ...selectApis(registrationApi, /^(fetch|get)/),
      ...selectApis(adminApi, /^fetch/),
    ]

    expect(apis.length).toBeGreaterThanOrEqual(22)
    await invokeApis(apis)

    const requestedUrls = vi.mocked(fetch).mock.calls.map(([url]) => String(url))
    expect(requestedUrls.some((url) => url.startsWith('/api/v1/quality/'))).toBe(true)
    expect(requestedUrls.some((url) => url.startsWith('/api/v1/registration/'))).toBe(true)
    expect(requestedUrls.some((url) => url.startsWith('/api/v1/identity/'))).toBe(true)
  })

  it('constructs all migrated quality, registration, regulatory, and warehouse client requests', async () => {
    const apis = [
      ...selectApis(qualityClientApi, /^fetch/),
      ...selectApis(registrationClientApi, /^fetch/),
      ...selectApis(regulatoryTrackerClientApi, /^(fetch|analyze|manual)/),
      ...selectApis(warehouseClientApi, /^fetch/),
    ]

    expect(apis.length).toBeGreaterThanOrEqual(70)
    await invokeApis(apis)

    const requestedUrls = vi.mocked(fetch).mock.calls.map(([url]) => String(url))
    expect(requestedUrls.some((url) => url.startsWith('/api/v1/quality/'))).toBe(true)
    expect(requestedUrls.some((url) => url.startsWith('/api/v1/registration/'))).toBe(true)
    expect(requestedUrls.some((url) => url.startsWith('/api/v1/warehouse/'))).toBe(true)
  })

  it('surfaces protected API failures instead of returning placeholder data', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ...successfulResponse(),
        ok: false,
        status: 403,
        statusText: 'Forbidden',
      }),
    )

    await expect(qualityExternalApi.fetchSuppliers()).rejects.toThrow('403')
    await expect(registrationApi.fetchModuleInfo()).rejects.toThrow('403')
    await expect(hrApi.fetchCandidateById('candidate-1')).rejects.toThrow(
      '获取候选人详情失败',
    )
  })

  it('covers optional query parameters, exports, and defensive search handling', async () => {
    const fetchMock = vi.mocked(fetch)
    fetchMock.mockImplementation(async (input) => {
      const url = String(input)
      if (url.includes('/annual-training-plans/plan-1/export')) {
        return new Response('docx', {
          status: 200,
          headers: { 'content-disposition': "attachment; filename*=utf-8''%E5%B9%B4%E5%BA%A6%E8%AE%A1%E5%88%92.docx" },
        })
      }
      return new Response(JSON.stringify({ code: 200, message: 'ok', data: [], meta: { total: 0, page: 2, page_size: 5 } }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    })

    await hrApi.fetchDepartments({ keyword: '质量', page: 2, page_size: 5 })
    await hrApi.fetchJobPostings({ keyword: '分析', page: 2, page_size: 5 })
    await hrApi.fetchCandidates({ keyword: '张', fit_level: '高', interview_status: '通过', job_id: 'job-1', page: 2, page_size: 5 })
    await hrApi.fetchFeishuMembers({ page: 2, page_size: 5, keyword: '张', department: '质量部', status: '1' })
    await hrApi.fetchAnnualTrainingPlans({ year: 2026, department: '质量部', page: 2, page_size: 5 })
    await hrApi.fetchPlanAttachments('plan-1')
    await hrApi.fetchPlanAttachmentSections('plan-1')
    await hrApi.fetchSectionPreview('section-1')
    await hrApi.fetchAttachmentPreview('attachment-1')
    await hrApi.fetchTrainingSession('session-1')
    await hrApi.fetchSessionDocuments('session-1')
    await hrApi.fetchTrainingDocument('document-1')
    const createObjectURL = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test')
    const revokeObjectURL = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
    await hrApi.exportAnnualTrainingPlanWord('plan-1', true)
    expect(createObjectURL).toHaveBeenCalled()
    expect(revokeObjectURL).toHaveBeenCalled()

    await expect(hrApi.searchFeishuMembers('')).resolves.toEqual([])
    fetchMock.mockResolvedValueOnce(new Response('unavailable', { status: 503 }))
    await expect(hrApi.searchFeishuMembers('张')).resolves.toEqual([])
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('status=1'))).toBe(true)
  })
})
