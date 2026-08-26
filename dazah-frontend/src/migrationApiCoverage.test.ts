/* @vitest-environment happy-dom */

import { beforeEach, describe, expect, it, vi } from 'vitest'

const fetchMock = vi.hoisted(() => vi.fn())

function jsonResponse(data: unknown = {}) {
  return new Response(JSON.stringify({ data }), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

describe('migration API adapter coverage', () => {
  beforeEach(() => {
    fetchMock.mockReset()
    fetchMock.mockImplementation(async () => jsonResponse({ items: [], data: [], total: 0 }))
    vi.stubGlobal('fetch', fetchMock)
    window.URL.createObjectURL = vi.fn(() => 'blob:test')
    window.URL.revokeObjectURL = vi.fn()
  })

  it('covers HR compatibility API adapters and their query builders', async () => {
    const hr = await import('@/lib/api/hr')
    await hr.fetchTrainingLedgersByDept('质量部', 2, 500)
    await hr.fetchEsgRecordsByDept('质量部', 2, 500)
    await hr.fetchHrFeishuAppSettings()
    await hr.fetchHrFeishuEntitySettings()
    await hr.fetchHrFeishuEntityTables('candidate', ' app-token ')
    await hr.fetchHrFeishuEntityFieldMappingBundle('candidate', { app_token: 'app', table_id: 'table' })
    await hr.fetchEmailConfig()
    await hr.fetchEmployees({ department: '质量部', status: 'active', keyword: '张', page: 2, page_size: 40 })
    await hr.fetchEmployeeById('employee-1')
    await hr.fetchEmployeeByNumber('E001')
    await hr.fetchDepartments({ keyword: '质量', page: 2, page_size: 40 })
    await hr.fetchTeams({ department_id: 'dept-1', keyword: '一组', page: 2, page_size: 40 })
    await hr.fetchOffboardingRecords({ employee_id: 'employee-1', keyword: '离职', page: 2, page_size: 40 })
    await hr.fetchOnboardingRecords({ employee_id: 'employee-1', department: '质量部', position: 'QA', is_employed: 'true', keyword: '张', page: 2, page_size: 40 })
    await hr.fetchDepartureRecords({ department: '质量部', offboarding_type: '主动', keyword: '张', sort_by: 'date', sort_order: 'desc', page: 2, page_size: 40 })
    await hr.fetchSyncStatus()
    await hr.syncFromFeishu()
    await hr.syncToFeishu('employee-1')
    await hr.syncOnboardingFromFeishu()
    await hr.syncDepartureFromFeishu()
    await hr.fetchTurnoverAnalysis()
    expect(hr.formatHrFeishuTestSummary(null)).toBe('测试完成')
    expect(hr.formatHrFeishuTestSummary({ success: true, message: 'OK' })).toContain('连接成功')
    expect(fetchMock).toHaveBeenCalled()
  })

  it('covers AI streaming, polling, file extraction and export adapters', async () => {
    const ai = await import('@/lib/api/ai')
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/stream')) {
        return new Response('data: {"reasoning_content":"推理"}\ndata: {"content":"答案","done":true}\n', { status: 200 })
      }
      if (url.includes('generate-written/job-1')) {
        return jsonResponse({ state: 'completed', result: { choice_questions: [], true_false_questions: [], fill_blank_questions: [] } })
      }
      if (url.includes('export-written')) return new Response('docx', { status: 200 })
      return jsonResponse({ job_id: 'job-1', text: '解析文本', filename: '培训.docx', analyzed: true })
    })
    const chunks: Array<[string, string]> = []
    const onDone = vi.fn()
    const onError = vi.fn()
    await ai.streamChat([{ role: 'user', content: '请分析' }], { page: 'hr' }, (type, text) => chunks.push([type, text]), onDone, onError)
    await ai.generateExamQuestions({ topic: 'GMP' })
    await ai.exportExam({ topic: 'GMP' })
    await ai.generateOralExamQuestions([{ name: '培训.pdf', content: 'base64', code: 'application/pdf' }], 3)
    await ai.submitWrittenExamGenerate({ topic: 'GMP' })
    await ai.pollWrittenExamGenerate('job-1', vi.fn(), { intervalMs: 0, timeoutMs: 100 })
    await ai.extractExamDocumentText(new File(['内容'], '培训.docx'))
    await ai.exportWrittenExam({ title: '试卷' })
    expect(chunks).toEqual([['reasoning', '推理'], ['content', '答案']])
    expect(onDone).toHaveBeenCalled()
    expect(onError).not.toHaveBeenCalled()
  })

  it('maps adapter HTTP failures to stable business errors', async () => {
    fetchMock.mockResolvedValueOnce(new Response('', { status: 500, statusText: 'Server Error' }))
    const hr = await import('@/lib/api/hr')
    await expect(hr.fetchEmployees()).rejects.toThrow('获取员工列表失败')
  })
})
