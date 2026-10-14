'use server'

import { getAuthHeaders } from '@/lib/auth'
import { serverApiUrl } from '@/lib/server-api'
import type { Feedback, FeedbackUpdate } from '@/lib/api/feedback'

async function feedbackWrite(path: string, method: string, body: FormData | string): Promise<{ success: true; data: Feedback } | { success: false; error: string }> {
  const headers = await getAuthHeaders()
  if (!headers.Authorization) return { success: false, error: '请重新登录后提交反馈' }
  if (body instanceof FormData) delete headers['Content-Type']
  try {
    const response = await fetch(serverApiUrl(path), { method, body, headers, cache: 'no-store', signal: AbortSignal.timeout(30_000) })
    if (!response.ok) {
      const result: { detail?: unknown } = await response.json()
      return { success: false, error: typeof result.detail === 'string' ? result.detail : '填写内容有误或权限不足，请检查后重试' }
    }
    const data: Feedback = await response.json()
    return { success: true, data }
  } catch {
    return { success: false, error: '反馈服务暂不可用，已保留填写内容，请稍后重试' }
  }
}

export async function submitFeedback(form: FormData) {
  return feedbackWrite('/identity/me/feedback', 'POST', form)
}

export async function processFeedback(id: string, payload: FeedbackUpdate) {
  if (!/^[0-9a-f-]{36}$/i.test(id)) return { success: false as const, error: '反馈编号无效' }
  return feedbackWrite(`/identity/admin/feedback/${id}`, 'PATCH', JSON.stringify(payload))
}
