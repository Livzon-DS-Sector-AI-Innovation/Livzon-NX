'use server'

import { revalidatePath } from 'next/cache'
import { API_BASE_URL, actionFetch } from './quality-shared'

import type {
  ValidationReviewCreatePayload,
  ValidationReviewFileUploaded,
  ValidationReviewRecord,
  ValidationReviewRunResult,
} from '@/types/quality'

const REVIEW_PATH = '/api/v1/quality/validation-reviews'

function revalidateReviewPaths() {
  revalidatePath('/quality/validation/ai-review')
}

export async function createValidationReview(
  data: ValidationReviewCreatePayload
): Promise<ValidationReviewRecord | null> {
  const result = await actionFetch<ValidationReviewRecord>(`${API_BASE_URL}${REVIEW_PATH}`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidateReviewPaths()
  return result
}

export async function uploadValidationReviewFile(
  reviewId: string,
  formData: FormData
): Promise<ValidationReviewFileUploaded | null> {
  const result = await actionFetch<ValidationReviewFileUploaded>(
    `${API_BASE_URL}${REVIEW_PATH}/${reviewId}/files`,
    {
      method: 'POST',
      body: formData,
    }
  )
  revalidateReviewPaths()
  return result
}

export async function runValidationReview(
  reviewId: string
): Promise<ValidationReviewRunResult | null> {
  const result = await actionFetch<ValidationReviewRunResult>(
    `${API_BASE_URL}${REVIEW_PATH}/${reviewId}/run`,
    { method: 'POST' }
  )
  revalidateReviewPaths()
  return result
}

export async function rerunValidationReview(
  reviewId: string
): Promise<ValidationReviewRunResult | null> {
  const result = await actionFetch<ValidationReviewRunResult>(
    `${API_BASE_URL}${REVIEW_PATH}/${reviewId}/rerun`,
    { method: 'POST' }
  )
  revalidateReviewPaths()
  return result
}

export async function deleteValidationReview(
  reviewId: string
): Promise<{ id: string } | null> {
  const result = await actionFetch<{ id: string }>(
    `${API_BASE_URL}${REVIEW_PATH}/${reviewId}`,
    { method: 'DELETE' }
  )
  revalidateReviewPaths()
  return result
}
