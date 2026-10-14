import type { components } from '@/types/generated/schema'

export type Feedback = components['schemas']['FeedbackResponse']
export type FeedbackList = components['schemas']['FeedbackListResponse']
export type FeedbackStatus = components['schemas']['FeedbackUpdate']['status']
export type FeedbackUpdate = components['schemas']['FeedbackUpdate']

export function feedbackPath(admin: boolean) {
  return `/api/v1/identity/${admin ? 'admin' : 'me'}/feedback`
}

export async function fetchFeedback(admin: boolean, page = 1, status?: FeedbackStatus, signal?: AbortSignal): Promise<FeedbackList> {
  const params = new URLSearchParams({ page: String(page), page_size: '10' })
  if (status) params.set('status', status)
  const response = await fetch(`${feedbackPath(admin)}?${params}`, { cache: 'no-store', signal })
  if (!response.ok) throw new Error(response.status === 403 ? '无权查看管理员反馈，请刷新页面确认权限' : '反馈列表读取失败，请重试')
  return response.json()
}
