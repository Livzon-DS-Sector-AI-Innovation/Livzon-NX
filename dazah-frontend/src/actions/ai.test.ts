import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ExamExportData } from '@/types/hr'

const mocks = vi.hoisted(() => ({ auth: vi.fn(), fetch: vi.fn() }))
vi.mock('@/lib/auth', () => ({ getAuthHeaders: mocks.auth }))
vi.mock('@/lib/server-api', () => ({ getServerApiBaseUrl: () => 'http://backend.test:8000' }))

import { exportExam, generateExamQuestions } from './ai'

const exam: ExamExportData = {
  title: '安全培训', examiner: '培训员', exam_date: '2026-10-28', assessment_date: '2026-10-28',
  choice_questions: [], true_false_questions: [],
}

beforeEach(() => {
  vi.resetAllMocks()
  mocks.auth.mockResolvedValue({ Authorization: 'Bearer synthetic', 'Content-Type': 'application/json' })
  vi.stubGlobal('fetch', mocks.fetch)
})
afterEach(() => vi.unstubAllGlobals())

describe('AI exam authentication and safe errors', () => {
  const actions = [
    { name: 'generate', run: () => generateExamQuestions(new File(['training'], 'training.txt')), error: '出题失败（503）' },
    { name: 'export', run: () => exportExam(exam), error: '导出失败（503）' },
  ]

  it.each(actions)('blocks $name without authentication before sending data', async ({ run }) => {
    mocks.auth.mockResolvedValue({ 'Content-Type': 'application/json' })
    await expect(run()).rejects.toThrow('未登录或登录已过期')
    expect(mocks.fetch).not.toHaveBeenCalled()
  })

  it.each(actions)('does not expose or read the upstream error body for $name', async ({ run, error }) => {
    const response = new Response('synthetic-secret: provider diagnostics', { status: 503 })
    const readBody = vi.spyOn(response, 'text')
    mocks.fetch.mockResolvedValue(response)
    await expect(run()).rejects.toMatchObject({ message: error })
    expect(readBody).not.toHaveBeenCalled()
    expect(response.bodyUsed).toBe(false)
  })

  it('sends authenticated multipart training material without a JSON content type', async () => {
    const data = { code: 200, message: '成功', data: { choice_questions: [], true_false_questions: [] } }
    mocks.fetch.mockResolvedValue(new Response(JSON.stringify(data)))
    await expect(generateExamQuestions(new File(['training'], 'training.txt'))).resolves.toEqual(data)
    const [url, init] = mocks.fetch.mock.calls[0]
    expect(url).toBe('http://backend.test:8000/api/v1/ai/exam/generate')
    expect(init).toEqual(expect.objectContaining({ method: 'POST', headers: { Authorization: 'Bearer synthetic' } }))
    expect(init.body).toBeInstanceOf(FormData)
    expect(init.body.get('file').name).toBe('training.txt')
    expect(await init.body.get('file').text()).toBe('training')
  })

  it('exports an authenticated JSON exam and preserves the returned document bytes', async () => {
    mocks.fetch.mockResolvedValue(new Response('synthetic-docx-bytes', {
      headers: { 'Content-Type': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' },
    }))
    const blob = await exportExam(exam)
    expect(blob.type).toBe('application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    expect(await blob.text()).toBe('synthetic-docx-bytes')
    expect(mocks.fetch).toHaveBeenCalledExactlyOnceWith('http://backend.test:8000/api/v1/ai/exam/export', {
      method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer synthetic' },
      body: JSON.stringify(exam),
    })
  })
})
