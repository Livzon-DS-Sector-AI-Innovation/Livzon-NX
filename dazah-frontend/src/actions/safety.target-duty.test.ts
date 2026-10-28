import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getAuthHeaders: vi
    .fn()
    .mockResolvedValue({ Authorization: 'Bearer test-token' }),
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

beforeEach(() => {
  vi.stubGlobal('document', {
    createElement: () => ({ click: () => {}, href: '', download: '' }),
    body: { appendChild: () => {}, removeChild: () => {} },
  })
  vi.stubGlobal('URL', {
    ...URL,
    createObjectURL: () => 'blob:x',
    revokeObjectURL: () => {},
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

describe('target duty actions（目标签约与履职评估）', () => {
  it('签约：列表/统计/增改删', async () => {
    const [u1] = await capture(() =>
      safety.getSafetyTargetAgreements({ page: 1, page_size: 10, year: 2026 }),
    )
    expect(u1).toContain('/api/v1/safety/safety-target-agreements')

    const [u2] = await capture(() => safety.getSafetyTargetAgreementStats(2026))
    expect(u2).toContain('/api/v1/safety/safety-target-agreements/stats')

    const [u3, i3] = await capture(() =>
      safety.createSafetyTargetAgreement({ year: 2026 } as never),
    )
    expect(u3).toContain('/api/v1/safety/safety-target-agreements')
    expect(i3?.method).toBe('POST')

    const [u4, i4] = await capture(() =>
      safety.updateSafetyTargetAgreement('a1', { status: 'signed' } as never),
    )
    expect(u4).toContain('/api/v1/safety/safety-target-agreements/a1')
    expect(i4?.method).toBe('PUT')

    const [, i5] = await capture(() => safety.deleteSafetyTargetAgreement('a1'))
    expect(i5?.method).toBe('DELETE')
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/safety/target-performance')
  })

  it('履职评估：列表/统计/模板/增改删', async () => {
    const [u1] = await capture(() =>
      safety.getSafetyDutyAssessments({ page: 1, page_size: 10, year: 2026 }),
    )
    expect(u1).toContain('/api/v1/safety/safety-duty-assessments')

    const [u2] = await capture(() => safety.getSafetyDutyAssessmentStats(2026))
    expect(u2).toContain('/api/v1/safety/safety-duty-assessments/stats')

    const [u3] = await capture(() =>
      safety.getSafetyDutyAssessmentTemplate('101一车间'),
    )
    expect(u3).toContain('/api/v1/safety/safety-duty-assessments/template')

    const [u4, i4] = await capture(() =>
      safety.createSafetyDutyAssessment({ year: 2026 } as never),
    )
    expect(i4?.method).toBe('POST')

    const [u5, i5] = await capture(() =>
      safety.updateSafetyDutyAssessment('d1', { score: 95 } as never),
    )
    expect(u5).toContain('/api/v1/safety/safety-duty-assessments/d1')
    expect(i5?.method).toBe('PUT')

    const [u6, i6] = await capture(() => safety.deleteSafetyDutyAssessment('d1'))
    expect(i6?.method).toBe('DELETE')
  })

  it('导入模板与导入提交（FormData）', async () => {
    const [u1] = await capture(() =>
      safety.downloadAgreementImportTemplate(),
    )
    expect(u1).toContain('/api/v1/safety/safety-target-agreements/import-template')

    const [u2, i2] = await capture(() =>
      safety.importAgreementSigns(new File(['x'], 'signs.xlsx')),
    )
    expect(u2).toContain('/api/v1/safety/safety-target-agreements/import')
    expect(i2?.method).toBe('POST')
    expect(i2?.body).toBeInstanceOf(FormData)

    const [u3] = await capture(() =>
      safety.downloadDutyAssessmentImportTemplate(2026, 1),
    )
    expect(u3).toContain('/api/v1/safety/safety-duty-assessments/import-template')

    const [u4, i4] = await capture(() =>
      safety.importDutyAssessmentResults(new File(['x'], 'duty.xlsx'), 2026, 1),
    )
    expect(u4).toContain('/api/v1/safety/safety-duty-assessments/import')
    expect(i4?.method).toBe('POST')
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/safety/target-performance')
  })

  it('模板下载的非 2xx 分支抛出错误', async () => {
    const textResponse = () =>
      Promise.resolve(new Response('网关错误', { status: 502, headers: { 'Content-Type': 'text/plain' } }))
    vi.stubGlobal('fetch', vi.fn(textResponse))
    await expect(safety.downloadAgreementImportTemplate()).rejects.toThrow()
    await expect(safety.downloadDutyAssessmentImportTemplate(2026, 1)).rejects.toThrow()
    vi.unstubAllGlobals()
  })
})
