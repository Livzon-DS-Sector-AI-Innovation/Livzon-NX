import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/auth', () => ({
  getAuthHeaders: vi.fn().mockResolvedValue({ 'X-Dazah-Page-Path': '/hr/training/sign-in-sheet' }),
}))
vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))

import { fetchDocumentDepartmentsServer } from './server/quality'
import { fetchDocumentEntries, lookupLatestDocument } from './client/quality'
import { resolveDocumentEntryContent } from '@/actions/quality'

afterEach(() => vi.unstubAllGlobals())

describe('document requests retain their own page authorization', () => {
  it('uses the document grant when the training page reads teaching documents', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: [] }), {
      headers: { 'content-type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetcher)
    await fetchDocumentEntries()
    expect(new Headers(fetcher.mock.calls.at(-1)?.[1]?.headers).get('X-Dazah-Page-Key')).toBe('quality:documents')
    fetcher.mockResolvedValue(new Response(JSON.stringify({ data: null })))
    await lookupLatestDocument('培训教材')
    expect(new Headers(fetcher.mock.calls.at(-1)?.[1]?.headers).get('X-Dazah-Page-Key')).toBe('quality:documents')
    fetcher.mockResolvedValue(new Response(JSON.stringify({ data: { results: [] } })))
    await resolveDocumentEntryContent(['培训教材'])
    expect(new Headers(fetcher.mock.calls.at(-1)?.[1]?.headers).get('X-Dazah-Page-Key')).toBe('quality:documents')
  })

  it('authenticates server rendering and keeps a denied request visible as an error', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ data: [{ id: 'dept', name: '质量部' }] })))
      .mockResolvedValueOnce(new Response('', { status: 403 }))
    vi.stubGlobal('fetch', fetcher)
    await expect(fetchDocumentDepartmentsServer()).resolves.toEqual([{ id: 'dept', name: '质量部' }])
    expect(new Headers(fetcher.mock.calls[0]?.[1]?.headers).get('X-Dazah-Page-Key')).toBe('quality:documents')
    await expect(fetchDocumentDepartmentsServer()).rejects.toThrow('403')
  })
})
