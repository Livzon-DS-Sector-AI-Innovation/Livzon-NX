import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  cookies: vi.fn().mockResolvedValue({
    get: vi.fn().mockReturnValue({ value: 'inspection-token' }),
  }),
  revalidatePath: vi.fn(),
}))

vi.mock('next/headers', () => ({ cookies: mocks.cookies }))
vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))

import {
  createInspectionFeishuRecord,
  deleteInspectionFeishuRecord,
  pullInspectionFeishuRecords,
  updateInspectionFeishuRecord,
} from './quality-inspection'

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

describe('quality inspection feishu record actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('creates a record via POST with wrapped fields payload', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ code: 200, data: { record_id: 'rec-1' } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const fields = { 检验编号: 'JY-001', 结论: '合格' }
    const result = await createInspectionFeishuRecord('finish_inspect', fields)

    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/quality/inspection/feishu/finish_inspect/records`,
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ fields }),
      }),
    )
    expect(result).toEqual({ record_id: 'rec-1' })
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/quality/inspection')
  })

  it('updates a record via PUT and URL-encodes ids', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ code: 200, data: { record_id: 'rec 2' } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await updateInspectionFeishuRecord('a b', 'rec/2', { 结论: '不合格' })

    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/quality/inspection/feishu/a%20b/records/rec%2F2`,
      expect.objectContaining({ method: 'PUT' }),
    )
  })

  it('deletes a record via DELETE', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ code: 200, data: { record_id: 'rec-3' } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await deleteInspectionFeishuRecord('entity', 'rec-3')

    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/quality/inspection/feishu/entity/records/rec-3`,
      expect.objectContaining({ method: 'DELETE' }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/quality')
  })

  it('pull sync reports failures and does not revalidate on error', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ detail: '飞书表未配置' }, 400),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(pullInspectionFeishuRecords('entity')).rejects.toThrow(
      '飞书表未配置',
    )
    expect(mocks.revalidatePath).not.toHaveBeenCalled()
  })

  it('pull posts to the entity pull endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ code: 200, data: { synced: 7, failed: 0 } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(pullInspectionFeishuRecords('entity')).resolves.toEqual({
      synced: 7,
      failed: 0,
    })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/quality/inspection/feishu/entity/pull`,
      expect.objectContaining({ method: 'POST' }),
    )
  })
})
