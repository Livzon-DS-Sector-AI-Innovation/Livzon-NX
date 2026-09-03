import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  fetchValidationReviewDetail,
  fetchValidationReviewJob,
  fetchValidationReviews,
} from './quality'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('quality client - validation review', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('fetches review list with pagination', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        code: 200,
        data: [{ id: 'review-1', status: 'completed' }],
        meta: { total: 1 },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchValidationReviews({ page: 2, page_size: 20 })).resolves.toEqual({
      items: [{ id: 'review-1', status: 'completed' }],
      total: 1,
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/quality/validation-reviews?page=2&page_size=20'
    )
  })

  it('returns empty items when data missing', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ code: 200 })))
    await expect(fetchValidationReviews()).resolves.toEqual({ items: [], total: 0 })
  })

  it('fetches review detail', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        code: 200,
        data: { id: 'review-1', status: 'draft', files: [] },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchValidationReviewDetail('review-1')).resolves.toEqual({
      id: 'review-1',
      status: 'draft',
      files: [],
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/quality/validation-reviews/review-1'
    )
  })

  it('fetches job status', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        code: 200,
        data: { job_id: 'job:1', state: 'running', progress: '启动中' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchValidationReviewJob('job:1')).resolves.toEqual({
      job_id: 'job:1',
      state: 'running',
      progress: '启动中',
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/quality/validation-reviews/job/job:1'
    )
  })

  it('throws parseError on failed request', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ message: '服务不可用' }), {
          status: 503,
          headers: { 'content-type': 'application/json' },
        })
      )
    )
    await expect(fetchValidationReviews()).rejects.toThrow(/503|服务不可用/)
  })
})
