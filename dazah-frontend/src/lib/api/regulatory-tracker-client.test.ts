import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  fetchAIAnalysis,
  fetchAIBatchAnalysis,
  fetchDocuments,
  fetchSummary,
  fetchSyncJobs,
} from './regulatory-tracker-client'
import type { RegulatoryDocument } from './regulatory-tracker-client'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

const makeDocument = (id: string, title: string): RegulatoryDocument => ({
  id,
  sourceId: 'source-1',
  channelId: 'channel-1',
  documentId: id,
  title,
  publishDate: null,
  statusText: null,
  classification: null,
  originalUrl: null,
  isNew: false,
  isRead: false,
  firstFoundAt: '2026-08-01T00:00:00.000Z',
  lastCheckedAt: null,
  createdAt: '2026-08-01T00:00:00.000Z',
})

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
    const doc = makeDocument('d1', '化学药药学研究指导原则')
    const analyzedDoc = {
      ...doc,
      aiRelevanceScore: 0.8,
      aiSummary: '高影响',
      aiKeyPoints: ['p1'],
      aiAnalyzedAt: '2026-08-01',
    }
    const fetchMock = vi.fn()
      .mockImplementationOnce(() => jsonResponse({ code: 200, message: 'success', data: { id: 'd1' } }))
      .mockImplementationOnce(() => jsonResponse({ code: 200, message: 'success', data: { items: [analyzedDoc] } }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchAIAnalysis(makeDocument('d1', '化学药药学研究指导原则'))
    expect(result.impactScore).toBe(80)
  })

  it('throws when AI analysis predict fails', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 500, message: '失败' }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(fetchAIAnalysis(makeDocument('d1', 'x'))).rejects.toThrow('失败')
  })

  it('fetches AI batch analysis and counts severity', async () => {
    const docs: RegulatoryDocument[] = [
      makeDocument('d1', '化学药研究指导原则'),
      makeDocument('d2', '生物药指导原则'),
      makeDocument('d3', '中药指导原则'),
    ]
    const analyzedDocs = [
      { ...docs[0], aiRelevanceScore: 0.9, aiSummary: '高', aiKeyPoints: [] },
      { ...docs[1], aiRelevanceScore: 0.3, aiSummary: '低', aiKeyPoints: [] },
      { ...docs[2], aiRelevanceScore: 0.05, aiSummary: '无', aiKeyPoints: [] },
    ]
    const fetchMock = vi.fn()
      .mockImplementationOnce(() => jsonResponse({ code: 200, message: 'success', data: {} }))
      .mockImplementationOnce(() => jsonResponse({ code: 200, message: 'success', data: { items: analyzedDocs } }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchAIBatchAnalysis(docs)
    expect(result.totalAnalyzed).toBe(3)
    expect(result.highImpact).toBe(1)
    expect(result.lowImpact).toBe(1)
  })
})
