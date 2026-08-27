import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  cookies: vi.fn().mockResolvedValue({
    get: vi.fn().mockReturnValue({ value: 'regulatory-token' }),
  }),
  revalidatePath: vi.fn(),
}))

vi.mock('next/headers', () => ({ cookies: mocks.cookies }))
vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))

import { analyzeRegulatoryDocument, analyzeRegulatoryDocuments, manualSyncRegulatoryTracker, markDocumentRead } from './regulatory-tracker'

describe('regulatory tracker server actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('keeps read and batch analysis writes on the tracker endpoints', async () => {
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(async () =>
        new Response(JSON.stringify({ data: { id: 'doc-1' } }), { status: 200 }),
      )
      .mockImplementationOnce(async () =>
        new Response(JSON.stringify({ data: { analyzed: 1, failed: 0, skipped: 0 } }), {
          status: 200,
        }),
      )
    vi.stubGlobal('fetch', fetchMock)

    await expect(markDocumentRead('doc/1')).resolves.toEqual({ id: 'doc-1' })
    await expect(analyzeRegulatoryDocuments(5)).resolves.toEqual({
      analyzed: 1,
      failed: 0,
      skipped: 0,
    })

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      expect.stringContaining('/api/v1/regulatory-documents/doc%2F1/read'),
      expect.objectContaining({ method: 'PATCH' }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      expect.stringContaining('/api/v1/regulatory-documents/analyze?limit=5'),
      expect.objectContaining({ method: 'POST' }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/registration/regulation')
  })

  it('maps tracker transport failures and uses default sync windows', async () => {
    const fetchMock = vi.fn().mockImplementation(async () => new Response('上游法规服务不可用', { status: 503, statusText: 'Unavailable' }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(markDocumentRead('doc-1')).rejects.toThrow('上游法规服务不可用')
    await expect(analyzeRegulatoryDocument('doc-1')).rejects.toThrow('上游法规服务不可用')
    await expect(analyzeRegulatoryDocuments()).rejects.toThrow('上游法规服务不可用')
    await expect(manualSyncRegulatoryTracker()).rejects.toThrow('上游法规服务不可用')
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('recentDays=7'))).toBe(true)
  })

  it('handles empty, single-document and manual-sync success responses', async () => {
    const fetchMock = vi.fn().mockImplementation(async (url: string) => {
      if (url.includes('doc-empty')) return new Response(null, { status: 204 })
      if (url.includes('/analyze')) return new Response(JSON.stringify({ data: { analyzed: true } }), { status: 200 })
      return new Response(JSON.stringify({ data: { synced: 2, failed: 0 } }), { status: 200 })
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(markDocumentRead('doc-empty')).resolves.toBeNull()
    await expect(analyzeRegulatoryDocument('doc-2')).resolves.toEqual({ analyzed: true })
    await expect(manualSyncRegulatoryTracker(14)).resolves.toEqual({ synced: 2, failed: 0 })
  })
})
