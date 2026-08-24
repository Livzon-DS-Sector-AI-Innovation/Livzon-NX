import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  cookies: vi.fn().mockResolvedValue({
    get: vi.fn().mockReturnValue({ value: 'regulatory-token' }),
  }),
  revalidatePath: vi.fn(),
}))

vi.mock('next/headers', () => ({ cookies: mocks.cookies }))
vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))

import { analyzeRegulatoryDocuments, markDocumentRead } from './regulatory-tracker'

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
})
