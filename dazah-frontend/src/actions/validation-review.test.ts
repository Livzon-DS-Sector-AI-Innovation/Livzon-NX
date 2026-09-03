import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/cache', () => ({
  revalidatePath: vi.fn(),
}))

vi.mock('./quality-shared', () => ({
  API_BASE_URL: 'http://backend',
  actionFetch: vi.fn(),
}))

import { actionFetch } from './quality-shared'
import {
  createValidationReview,
  deleteValidationReview,
  rerunValidationReview,
  runValidationReview,
  uploadValidationReviewFile,
} from './validation-review'

const mockedActionFetch = vi.mocked(actionFetch)

describe('validation-review server actions', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('createValidationReview posts review payload', async () => {
    mockedActionFetch.mockResolvedValue({ id: 'review-1' })
    const result = await createValidationReview({
      review_mode: 'upload',
      title: '测试',
    })
    expect(result).toEqual({ id: 'review-1' })
    expect(mockedActionFetch).toHaveBeenCalledWith(
      'http://backend/api/v1/quality/validation-reviews',
      { method: 'POST', body: JSON.stringify({ review_mode: 'upload', title: '测试' }) }
    )
  })

  it('uploadValidationReviewFile posts FormData', async () => {
    mockedActionFetch.mockResolvedValue({ id: 'file-1' })
    const formData = new FormData()
    formData.append('file', new Blob(['x']))
    const result = await uploadValidationReviewFile('review-1', formData)
    expect(result).toEqual({ id: 'file-1' })
    expect(mockedActionFetch).toHaveBeenCalledWith(
      'http://backend/api/v1/quality/validation-reviews/review-1/files',
      { method: 'POST', body: formData }
    )
  })

  it('runValidationReview posts run', async () => {
    mockedActionFetch.mockResolvedValue({ job_id: 'job:1', review_id: 'review-1' })
    const result = await runValidationReview('review-1')
    expect(result?.job_id).toBe('job:1')
    expect(mockedActionFetch).toHaveBeenCalledWith(
      'http://backend/api/v1/quality/validation-reviews/review-1/run',
      { method: 'POST' }
    )
  })

  it('rerunValidationReview posts rerun', async () => {
    mockedActionFetch.mockResolvedValue({ job_id: 'job:2', review_id: 'review-1' })
    const result = await rerunValidationReview('review-1')
    expect(result?.job_id).toBe('job:2')
    expect(mockedActionFetch).toHaveBeenCalledWith(
      'http://backend/api/v1/quality/validation-reviews/review-1/rerun',
      { method: 'POST' }
    )
  })

  it('deleteValidationReview deletes', async () => {
    mockedActionFetch.mockResolvedValue({ id: 'review-1' })
    const result = await deleteValidationReview('review-1')
    expect(result).toEqual({ id: 'review-1' })
    expect(mockedActionFetch).toHaveBeenCalledWith(
      'http://backend/api/v1/quality/validation-reviews/review-1',
      { method: 'DELETE' }
    )
  })
})