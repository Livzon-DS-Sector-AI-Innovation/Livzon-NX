import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  fetchDeptApprovalConfigNames,
  fetchEmployeeDepartments,
  fetchOnboardingAttachmentContent,
  fetchTrainingDeptMappings,
} from './hr'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('hr client onboarding/dept fetchers', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('downloads onboarding attachment content as blob', async () => {
    const blob = new Blob(['png'], { type: 'image/png' })
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, blob: () => blob })
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchOnboardingAttachmentContent('rec 1', 'tok/a')).resolves.toBe(blob)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/hr/onboarding/rec 1/attachments/tok/a/content',
    )
  })

  it('surfaces backend message on attachment download failure', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({ message: '非归属附件' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchOnboardingAttachmentContent('id', 'tok')).rejects.toThrow(
      '非归属附件',
    )
  })

  it('falls back to generic error when attachment body is unparseable', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      json: async () => {
        throw new Error('not json')
      },
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchOnboardingAttachmentContent('id', 'tok')).rejects.toThrow(
      '附件下载失败',
    )
  })

  it('fetches dept approval config names from data envelope', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ code: 200, data: ['质量管理部', '生产部'] }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchDeptApprovalConfigNames()).resolves.toEqual([
      '质量管理部',
      '生产部',
    ])
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/hr/dept-approval-configs/names',
      { cache: 'no-store' },
    )
  })

  it('throws on dept names failure', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}, 500))
    vi.stubGlobal('fetch', fetchMock)
    await expect(fetchDeptApprovalConfigNames()).rejects.toThrow('获取部门名单失败')
  })

  it('maps employee departments from stats distribution', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        code: 200,
        data: {
          department_distribution: [
            { department: '行政部', count: 3 },
            { department: '生产部', count: 9 },
          ],
        },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchEmployeeDepartments()).resolves.toEqual(['行政部', '生产部'])
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/hr/employees/stats', {
      cache: 'no-store',
    })
  })

  it('prefers message then detail for employee departments error', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ detail: '权限不足' }, 403))
    vi.stubGlobal('fetch', fetchMock)
    await expect(fetchEmployeeDepartments()).rejects.toThrow('权限不足')
  })

  it('parses dept mapping items including the person mapping type', async () => {
    const item = {
      id: 'map-1',
      source_name: '质量部',
      target_name: 'QA',
      match_level: 'both',
      mapping_type: 'person',
      priority: 1,
      enabled: true,
      remark: null,
      created_at: null,
      updated_at: null,
    }
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ data: [item] }))
    vi.stubGlobal('fetch', fetchMock)

    const mappings = await fetchTrainingDeptMappings()
    expect(mappings).toHaveLength(1)
    expect(mappings[0]).toMatchObject({
      source_name: '质量部',
      mapping_type: 'person',
    })
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/hr/training/dept-mappings', {
      cache: 'no-store',
    })
  })
})
