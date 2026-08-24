import { beforeEach, describe, expect, it, vi } from 'vitest'

import * as adminApi from '@/lib/api/client/admin'
import * as hrApi from '@/lib/api/client/hr'
import * as qualityExternalApi from '@/lib/api/quality-external'
import * as qualityOosOotApi from '@/lib/api/quality-oos-oot'
import * as registrationApi from '@/lib/api/registration'

type AsyncApi = (...args: unknown[]) => Promise<unknown>

const dummyArgument: unknown = new Proxy(() => undefined, {
  get: (_target, property) => {
    if (property === Symbol.toPrimitive) return () => 'demo'
    if (property === 'toString') return () => 'demo'
    return dummyArgument
  },
})

function successfulResponse(): Response {
  const body = {
    code: 200,
    message: 'ok',
    data: {
      items: [],
      menu_ids: [],
      result: [],
      stages: {},
      total: 0,
      url: '/protected-download',
    },
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
    const args = Array.from(
      { length: Math.max(api.length, 1) },
      () => dummyArgument,
    )
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
})
