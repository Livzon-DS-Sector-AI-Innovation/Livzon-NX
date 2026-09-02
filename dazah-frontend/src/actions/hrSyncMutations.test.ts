import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  cookies: vi.fn().mockResolvedValue({
    get: vi.fn().mockReturnValue({ value: 'hr-token' }),
  }),
  revalidatePath: vi.fn(),
}))

vi.mock('next/headers', () => ({
  cookies: mocks.cookies,
  headers: vi.fn(async () => new Headers()),
}))
vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))

import {
  clearDeptScopeAction,
  createSecondLevelTraining,
  deleteOnboardingAction,
  saveDeptScopeAction,
  syncDepartureFromFeishuAction,
  syncOnboardingFromFeishuAction,
  uploadOnboardingAttachmentAction,
} from './hr'

const API_BASE =
  process.env.API_BASE_URL ||
  process.env.INTERNAL_API_BASE_URL ||
  'http://dazah-backend-app-1:8000'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('hr training-session / onboarding / dept-scope actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('createSecondLevelTraining posts record id and unwraps data', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ code: 200, data: { id: 's1', copied_doc_types: [], parent_record_id: 'p1' } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(createSecondLevelTraining('r1')).resolves.toEqual({
      id: 's1',
      copied_doc_types: [],
      parent_record_id: 'p1',
    })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/hr/training-sessions/from-ledger`,
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ record_id: 'r1' }) }),
    )
  })

  it('createSecondLevelTraining falls back through message, detail, generic', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ message: '已达上限' }, 400)))
    await expect(createSecondLevelTraining('r1')).rejects.toThrow('已达上限')

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail: '部门未配置' }, 400)))
    await expect(createSecondLevelTraining('r1')).rejects.toThrow('部门未配置')

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('oops', { status: 500 })))
    await expect(createSecondLevelTraining('r1')).rejects.toThrow('创建二级培训会话失败')
  })

  it('deleteOnboardingAction returns body and revalidates list', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ code: 200, message: 'ok' }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(deleteOnboardingAction('ob 1')).resolves.toEqual({ code: 200, message: 'ok' })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/hr/onboarding/ob 1`,
      expect.objectContaining({ method: 'DELETE' }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/hr/onboarding')
  })

  it('deleteOnboardingAction surfaces backend message on failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ message: '记录不存在' }, 404)))
    await expect(deleteOnboardingAction('x')).rejects.toThrow('记录不存在')
    expect(mocks.revalidatePath).not.toHaveBeenCalled()
  })

  it('uploadOnboardingAttachmentAction posts multipart and returns data', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ code: 200, data: { file_token: 'tok-9', name: 'a.png' } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const file = new File(['x'], 'a.png', { type: 'image/png' })
    await expect(uploadOnboardingAttachmentAction(file)).resolves.toEqual({
      file_token: 'tok-9',
      name: 'a.png',
    })
    const [, init] = fetchMock.mock.calls[0]
    expect(init?.method).toBe('POST')
    expect(init?.body).toBeInstanceOf(FormData)
    expect((init?.body as FormData).get('file')).toBeInstanceOf(File)
  })

  it('uploadOnboardingAttachmentAction falls back to empty token on missing data', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ code: 200 })))
    const file = new File(['x'], 'b.pdf', { type: 'application/pdf' })
    await expect(uploadOnboardingAttachmentAction(file)).resolves.toEqual({
      file_token: '',
      name: 'b.pdf',
    })
  })

  it('uploadOnboardingAttachmentAction throws backend message on failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ message: '文件过大' }, 413)))
    const file = new File(['x'], 'big.bin')
    await expect(uploadOnboardingAttachmentAction(file)).rejects.toThrow('文件过大')
  })

  it('saveDeptScopeAction PUTs depts with optional user meta', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ code: 200, data: { user_id: 'u1', visible_depts: ['生产部'] } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(
      saveDeptScopeAction('u1', ['生产部'], { user_name: '张三', user_department: '质量管理部' }),
    ).resolves.toEqual({ user_id: 'u1', visible_depts: ['生产部'] })
    const [, init] = fetchMock.mock.calls[0]
    expect(init?.method).toBe('PUT')
    expect(JSON.parse(String(init?.body))).toEqual({
      visible_depts: ['生产部'],
      user_name: '张三',
      user_department: '质量管理部',
    })
  })

  it('saveDeptScopeAction error branch prefers message then detail then generic', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail: '无权限' }, 403)))
    await expect(saveDeptScopeAction('u1', [])).rejects.toThrow('无权限')

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('x', { status: 500 })))
    await expect(saveDeptScopeAction('u1', [])).rejects.toThrow('保存可见部门配置失败')
  })

  it('clearDeptScopeAction deletes silently and raises on failure', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(clearDeptScopeAction('u9')).resolves.toBeUndefined()
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/hr/dept-scopes/u9`,
      expect.objectContaining({ method: 'DELETE' }),
    )

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ message: '配置不存在' }, 404)))
    await expect(clearDeptScopeAction('u9')).rejects.toThrow('配置不存在')
  })

  it('sync onboarding/departure ledgers from feishu post, revalidate and map errors', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'ok' }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(syncOnboardingFromFeishuAction()).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/hr/onboarding-records/sync-from-feishu`,
      expect.objectContaining({ method: 'POST' }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/hr/onboarding')

    await syncDepartureFromFeishuAction()
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/hr/departure-records/sync-from-feishu`,
      expect.objectContaining({ method: 'POST' }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/hr/departure')

    vi.stubGlobal('fetch', vi.fn(() => jsonResponse({ message: '飞书限频' }, 429)))
    await expect(syncOnboardingFromFeishuAction()).rejects.toThrow('飞书限频')
    await expect(syncDepartureFromFeishuAction()).rejects.toThrow('飞书限频')

    vi.stubGlobal('fetch', vi.fn(() => new Response('x', { status: 500 })))
    await expect(syncOnboardingFromFeishuAction()).rejects.toThrow('从飞书同步入职台账失败')
    await expect(syncDepartureFromFeishuAction()).rejects.toThrow('从飞书同步离职台账失败')
  })
})
