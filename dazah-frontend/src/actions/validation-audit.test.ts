import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getServerApiBaseUrl: vi.fn(() => 'http://backend.test'),
  getAuthHeaders: vi.fn().mockResolvedValue({
    'Content-Type': 'application/json',
    Authorization: 'Bearer server-token',
    'X-Dazah-Page-Path': '/registration/validation-audit',
  }),
  revalidatePath: vi.fn(),
}))

vi.mock('@/lib/auth', () => ({ getAuthHeaders: mocks.getAuthHeaders }))
vi.mock('@/lib/server-api', () => ({ getServerApiBaseUrl: mocks.getServerApiBaseUrl }))
vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))

import {
  createValidationAuditTask,
  deleteValidationAuditTask,
  fetchFilesServer,
  fetchIssuesServer,
  fetchReportServer,
  fetchTaskByIdServer,
  fetchTasksServer,
  parseValidationAuditFiles,
  runValidationAudit,
  uploadValidationAuditFiles,
} from './validation-audit'
import { summarizeUpload } from '@/components/registration/validation-audit/upload-feedback'

describe('validation audit server actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    vi.clearAllMocks()
  })

  it('creates and deletes audit tasks through the registration audit API', async () => {
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(async () =>
        new Response(JSON.stringify({ message: '创建成功', data: { id: 'task-1' } }), {
          status: 200,
        }),
      )
      .mockImplementationOnce(async () =>
        new Response(JSON.stringify({ message: '删除成功', data: null }), { status: 200 }),
      )
    vi.stubGlobal('fetch', fetchMock)

    await expect(createValidationAuditTask({ product_name: '产品A' } as never)).resolves.toEqual({
      ok: true,
      data: { id: 'task-1' },
    })
    await expect(deleteValidationAuditTask('task-1')).resolves.toEqual({
      ok: true,
      data: null,
    })

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      'http://backend.test/api/v1/registration/validation-audit/tasks',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          Authorization: 'Bearer server-token',
          'X-Dazah-Page-Path': '/registration/validation-audit',
        }),
      }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      'http://backend.test/api/v1/registration/validation-audit/tasks/task-1',
      expect.objectContaining({
        method: 'DELETE',
        headers: expect.objectContaining({
          Authorization: 'Bearer server-token',
          'X-Dazah-Page-Path': '/registration/validation-audit',
        }),
      }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/registration/validation-audit')
  })

  it('returns safe failure results for audit reads, writes, and malformed responses', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const fetchMock = vi.fn(() => new Response('内部详情', { status: 503 }))
    vi.stubGlobal('fetch', fetchMock)
    for (const read of [
      fetchTasksServer({ page: 2, page_size: 5 }), fetchTaskByIdServer('task-1'),
      fetchFilesServer('task-1'), fetchIssuesServer('task-1', 'critical'), fetchReportServer('task-1'),
    ]) {
      await expect(read).resolves.toMatchObject({
        ok: false, message: '暂时无法读取验证审核数据，请刷新后重试', reference: expect.any(String),
      })
    }
    await expect(runValidationAudit('task-1')).resolves.toMatchObject({
      ok: false, message: '暂未确认验证审核执行结果，请先查看业务记录后再决定是否重试', reference: expect.any(String),
    })
    expect(mocks.revalidatePath).not.toHaveBeenCalled()
  })

  it('distinguishes missing data from access failures in detail reads', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(new Response(null, { status: 404 }))
      .mockResolvedValueOnce(new Response(null, { status: 404 }))
      .mockResolvedValueOnce(new Response(null, { status: 403 })))
    await expect(fetchTaskByIdServer('missing')).resolves.toEqual({ ok: true, data: null })
    await expect(fetchReportServer('task-1')).resolves.toEqual({ ok: true, data: null })
    await expect(fetchTaskByIdServer('task-1')).resolves.toEqual({ ok: false, message: '没有执行此操作的权限，请联系管理员' })
  })

  it.each([
    [uploadValidationAuditFiles, 400, 'VALIDATION_AUDIT_FILE_LIMIT', '本次上传的文件过多，请分批上传'],
    [parseValidationAuditFiles, 409, 'VALIDATION_AUDIT_NO_FILES', '请先上传审核文件，再执行解析'],
    [parseValidationAuditFiles, 422, 'VALIDATION_AUDIT_FILE_UNREADABLE', '无法读取审核文件，请检查文件是否损坏或受密码保护，必要时联系管理员'],
    [runValidationAudit, 409, 'VALIDATION_AUDIT_NO_FILES', '请上传并解析审核文件，再执行审核'],
    [runValidationAudit, 409, 'VALIDATION_AUDIT_NO_PARSED_FILES', '请先解析审核文件，再执行审核'],
    [runValidationAudit, 409, 'VALIDATION_AUDIT_CROSS_FILES_REQUIRED', '联合审核需要方案和报告，请补齐并解析两类文件'],
    [runValidationAudit, 429, null, '操作过于频繁，请稍后重试'],
    [runValidationAudit, 409, 'UNKNOWN', '数据已发生变化，请刷新后重试'],
    [runValidationAudit, 403, 'VALIDATION_AUDIT_CROSS_FILES_REQUIRED', '没有执行此操作的权限，请联系管理员'],
    [deleteValidationAuditTask, 404, null, '请求的内容不存在或已被删除，请刷新后重试'],
  ] as const)('maps the expected HTTP failures from %s', async (call, status, errorCode, message) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      message: '上游内部响应', detail: errorCode ? { error_code: errorCode } : null,
    }), { status })))
    await expect(call('task-1', new FormData())).resolves.toEqual({ ok: false, message })
    expect(mocks.revalidatePath).not.toHaveBeenCalled()
  })

  it('keeps partial upload results and maps each failed item by status', async () => {
    const items = [
      { status: 'success', filename: 'good.pdf', file_id: '1', file_size: 24 },
      { status: 'failed', filename: 'large.pdf', status_code: 413, error: '上游内部响应' },
    ] as const
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: items })))
    vi.stubGlobal('fetch', fetcher)
    const formData = new FormData()
    const result = await uploadValidationAuditFiles('task-1', formData)
    expect(result).toEqual({ ok: true, data: items })
    if (!result.ok) throw new Error('Upload failed')
    expect(summarizeUpload(result.data)).toEqual({
      succeeded: 1, failedIndexes: new Set([1]),
      message: '上传成功 1 个，失败 1 个。large.pdf：文件过大，请缩小文件后重试',
    })
    expect(fetcher.mock.calls[0][1].headers['Content-Type']).toBeUndefined()
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/registration/validation-audit/task-1')
  })
})
