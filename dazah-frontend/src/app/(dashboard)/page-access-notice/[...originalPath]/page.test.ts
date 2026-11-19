import { headers } from 'next/headers'
import { describe, expect, it, vi } from 'vitest'
import { PAGE_ACCESS_NOTICE_HEADER, PAGE_NOT_FOUND } from '@/lib/page-access-notice'
import PageAccessNoticePage from './page'

vi.mock('next/headers', () => ({ headers: vi.fn() }))

describe('page access notice route', () => {
  it.each([undefined, 'unknown', PAGE_NOT_FOUND])('uses the dashboard 404 boundary for %s', async (reason) => {
    const requestHeaders = new Headers()
    if (reason) requestHeaders.set(PAGE_ACCESS_NOTICE_HEADER, reason)
    vi.mocked(headers).mockResolvedValue(requestHeaders)

    await expect(PageAccessNoticePage()).rejects.toMatchObject({ digest: 'NEXT_HTTP_ERROR_FALLBACK;404' })
  })
})
