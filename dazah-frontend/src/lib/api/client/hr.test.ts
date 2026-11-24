import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  exportPositionTrainingConfirmation,
  fetchDeptApprovalConfigNames,
  fetchEmployeeDepartments,
  fetchEmployeeStats,
  fetchNewEmployeeTrainingCandidates,
  fetchOnboardingAttachmentContent,
  fetchTrainingDeptMappings,
  fetchTrainingSignInEmployees,
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

  it('looks up exact-name candidates through the new-employee training page endpoint', async () => {
    const employee = { id: 'employee-1', name: '李四', department: '培训部', sub_department: null, position: '操作员', hire_date: '2026-11-24', employee_number: 'E01' }
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ code: 200, data: [employee] }))
      .mockResolvedValueOnce(jsonResponse({ code: 403 }, 403))
    vi.stubGlobal('fetch', fetchMock)
    const controller = new AbortController()

    await expect(fetchNewEmployeeTrainingCandidates('李四', controller.signal)).resolves.toEqual([employee])
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/hr/new-employee-training/employee-candidates?name=%E6%9D%8E%E5%9B%9B',
      { cache: 'no-store', signal: controller.signal },
    )
    await expect(fetchNewEmployeeTrainingCandidates('李四')).rejects.toThrow('匹配新员工档案失败')
  })

  it('reads every scoped page of the sign-in employee directory', async () => {
    const first = Array.from({ length: 200 }, (_, index) => ({
      name: `测试员工${index}`, department: '质量部', sub_department: null,
    }))
    const last = { name: '末页员工', department: '生产部', sub_department: '一车间' }
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ data: first, meta: { total: 201 } }))
      .mockResolvedValueOnce(jsonResponse({ data: [last], meta: { total: 201 } }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(fetchTrainingSignInEmployees()).resolves.toEqual([...first, last])
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      '/api/v1/hr/training-sign-in/employees?page=1&page_size=200',
      '/api/v1/hr/training-sign-in/employees?page=2&page_size=200',
    ])
  })

  it('downloads the APP14 workbook for the current training plan', async () => {
    const mediaType = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    const fetchMock = vi.fn().mockResolvedValue(new Response('workbook', {
      headers: { 'content-type': mediaType },
    }))
    vi.stubGlobal('fetch', fetchMock)

    const workbook = await exportPositionTrainingConfirmation('plan-1')

    expect(workbook.type).toBe(mediaType)
    await expect(workbook.text()).resolves.toBe('workbook')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/hr/new-employee-training/plans/plan-1/export-confirmation',
      { cache: 'no-store' },
    )
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

describe('hr employee stats client', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('fetchEmployeeStats requests stats and returns the payload', async () => {
    const payload = { code: 200, data: { total: 12, active: 10, offline: 2 } }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(payload)))
    const result = await fetchEmployeeStats()
    expect(result).toEqual(payload)
    expect(String(vi.mocked(fetch).mock.calls[0][0])).toBe(
      '/api/v1/hr/employees/stats',
    )
  })
})
