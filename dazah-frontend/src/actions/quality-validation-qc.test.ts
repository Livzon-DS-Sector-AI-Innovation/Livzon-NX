import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  cookies: vi.fn().mockResolvedValue({
    get: vi.fn().mockReturnValue({ value: 'qc-token' }),
  }),
  revalidatePath: vi.fn(),
}))

vi.mock('next/headers', () => ({ cookies: mocks.cookies }))
vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))

import {
  createQcValidationRecord,
  deleteQcValidationRecord,
  updateQcValidationRecord,
} from './quality-validation-qc'

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

describe('quality validation qc actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('creates a qc validation record with year query', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ code: 200, data: { record_id: 'rec-1' } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const fields = { 检验项目: '含量', 结论: '合格' }
    await expect(
      createQcValidationRecord(2026, fields),
    ).resolves.toEqual({ record_id: 'rec-1' })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/quality/validation-qc/records?year=2026`,
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ fields }),
      }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith(
      '/quality/validation/qc-validation',
    )
  })

  it('throws when create result is empty', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ code: 200 })))
    await expect(createQcValidationRecord(2026, {})).rejects.toThrow(
      '未收到QC验证创建结果',
    )
  })

  it('updates a qc validation record with url-encoded id and year', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ code: 200, data: { record_id: 'rec/2' } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(
      updateQcValidationRecord(2026, 'rec/2', { 结论: '不合格' }),
    ).resolves.toEqual({ record_id: 'rec/2' })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/quality/validation-qc/records/rec%2F2?year=2026`,
      expect.objectContaining({ method: 'PUT' }),
    )
  })

  it('deletes a qc validation record', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ code: 200, data: { record_id: 'rec-3' } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(deleteQcValidationRecord(2025, 'rec-3')).resolves.toEqual({
      record_id: 'rec-3',
    })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/quality/validation-qc/records/rec-3?year=2025`,
      expect.objectContaining({ method: 'DELETE' }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/quality')
  })

  it('throws when delete result is empty and does not revalidate', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ code: 200 })))
    await expect(deleteQcValidationRecord(2026, 'x')).rejects.toThrow(
      '未收到QC验证删除结果',
    )
    expect(mocks.revalidatePath).not.toHaveBeenCalled()
  })
})
