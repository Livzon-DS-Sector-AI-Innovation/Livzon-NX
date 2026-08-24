import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  fetchAIAnalysis,
  fetchAIBatchAnalysis,
  fetchDocuments,
  fetchSummary,
  fetchSyncJobs,
} from './regulatory-tracker-client'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('regulatory tracker client', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('fetches the summary', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { total: 3 } }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchSummary()
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/regulatory-tracker/summary')
    expect(result).toMatchObject({ total: 3 })
  })

  it('fetches documents with search params', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { items: [] } }))
    vi.stubGlobal('fetch', fetchMock)

    await fetchDocuments({ page: 1, pageSize: 20, keyword: 'GMP' })
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/regulatory-documents?'),
    )
  })

  it('fetches sync jobs with pagination', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { items: [] } }))
    vi.stubGlobal('fetch', fetchMock)

    await fetchSyncJobs(2, 50)
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/sync-jobs?page=2&pageSize=50')
  })

  it('fetches AI analysis for a doc', async () => {
    const doc = { id: 'd1', title: '化学药药学研究指导原则', aiRelevanceScore: 0.8, aiSummary: '高影响', aiKeyPoints: ['p1'], aiAnalyzedAt: '2026-08-01' }
    const fetchMock = vi.fn()
      .mockImplementationOnce(() => jsonResponse({ code: 200, message: 'success', data: { id: 'd1' } }))
      .mockImplementationOnce(() => jsonResponse({ code: 200, message: 'success', data: { items: [doc] } }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchAIAnalysis({ id: 'd1', title: '化学药药学研究指导原则' } as any)
    expect(result.impactScore).toBe(80)
  })

  it('throws when AI analysis predict fails', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 500, message: '失败' }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(fetchAIAnalysis({ id: 'd1', title: 'x' } as any)).rejects.toThrow('失败')
  })

  it('fetches AI batch analysis and counts severity', async () => {
    const docs = [
      { id: 'd1', title: '化学药研究指导原则', aiRelevanceScore: 0.9, aiSummary: '高', aiKeyPoints: [] },
      { id: 'd2', title: '生物药指导原则', aiRelevanceScore: 0.3, aiSummary: '低', aiKeyPoints: [] },
      { id: 'd3', title: '中药指导原则', aiRelevanceScore: 0.05, aiSummary: '无', aiKeyPoints: [] },
    ]
    const fetchMock = vi.fn()
      .mockImplementationOnce(() => jsonResponse({ code: 200, message: 'success', data: {} }))
      .mockImplementationOnce(() => jsonResponse({ code: 200, message: 'success', data: { items: docs } }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchAIBatchAnalysis(docs as any)
    expect(result.totalAnalyzed).toBe(3)
    expect(result.highImpact).toBe(1)
    expect(result.lowImpact).toBe(1)
  })
})
