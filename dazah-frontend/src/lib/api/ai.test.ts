import { afterEach, describe, expect, it, vi } from 'vitest'

import { exportExam, generateExamQuestions } from './ai'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('ai lib api', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('generates exam questions and returns data payload', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { questions: ['q1'] } }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await generateExamQuestions({ department: '102一车间' })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/ai/exam/generate',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ department: '102一车间' }),
      }),
    )
    expect(result).toEqual({ questions: ['q1'] })
  })

  it('exports exam and returns data payload', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { url: '/export.xlsx' } }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await exportExam({ exam_id: 'e-1' })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/ai/exam/export',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(result).toEqual({ url: '/export.xlsx' })
  })

  it('throws when the export request fails', async () => {
    const fetchMock = vi.fn(() => new Response('server error', { status: 500 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(exportExam({ exam_id: 'e-1' })).rejects.toThrow('请求失败: 500')
  })
})
