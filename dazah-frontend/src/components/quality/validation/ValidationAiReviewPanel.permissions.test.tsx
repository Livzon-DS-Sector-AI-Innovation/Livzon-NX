/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { App, ConfigProvider } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/auth'

vi.mock('next/navigation', () => ({ usePathname: () => '/quality/validation/ai-review' }))
const actions = vi.hoisted(() => ({
  createValidationReview: vi.fn(), deleteValidationReview: vi.fn(),
  rerunValidationReview: vi.fn(), runValidationReview: vi.fn(), uploadValidationReviewFile: vi.fn(),
}))
vi.mock('@/actions/validation-review', () => actions)
vi.mock('@/lib/api/client/quality', () => ({
  fetchValidationReviews: vi.fn(async () => ({ items: [{ id: 'review1', title: '测试审核', status: 'completed', review_mode: 'upload', file_count: 0 }], total: 1 })),
  fetchValidationReviewDetail: vi.fn(async () => ({ id: 'review1', title: '测试审核', status: 'completed', review_mode: 'upload', files: [], findings: [], basis_used: [] })),
  fetchValidationReviewJob: vi.fn(),
}))
import { ValidationAiReviewPanel } from './ValidationAiReviewPanel'

afterEach(() => useAuthStore.getState().clearUser())
it('gates review creation/rerun, deletion and export independently and honors revocation', async () => {
  const container = document.createElement('div')
  document.body.append(container)
  const root = createRoot(container)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const authorize = (operate: boolean, sensitive: string[] = []) => act(() => useAuthStore.getState().setUser({
    id: 'tester', name: '测试用户', role: 'user', permissions: ['*', 'quality:write'],
    page_permissions: [{ page_key: 'quality:validation:validation-ai-review', module_code: 'quality',
      permissions: operate ? ['access', 'query', 'operate'] : ['access', 'query'],
      sensitive_actions: sensitive, data_scope: { scope_type: 'all' }, source: 'user' }],
  }))
  const button = (label: string) => {
    const result = [...document.body.querySelectorAll('button')].find((item) =>
      item.getAttribute('aria-label') === label || item.textContent?.replace(/\s/g, '') === label)
    expect(result, label).toBeTruthy()
    return result!
  }
  try {
    authorize(false)
    await act(async () => root.render(<ConfigProvider theme={{ token: { motion: false } }}><App>
      <QueryClientProvider client={client}><ValidationAiReviewPanel /></QueryClientProvider>
    </App></ConfigProvider>))
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 60)) })
    expect(button('新建审核').disabled).toBe(true)
    expect(button('重新审核').disabled).toBe(true)
    expect(button('删除审核记录').disabled).toBe(true)
    await act(async () => button('查看').click())
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 60)) })
    expect(button('导出报告').disabled).toBe(true)
    authorize(true)
    expect(button('新建审核').disabled).toBe(false)
    expect(button('重新审核').disabled).toBe(false)
    expect(button('删除审核记录').disabled).toBe(true)
    expect(button('导出报告').disabled).toBe(true)
    authorize(true, ['delete', 'sensitive_export'])
    expect(button('删除审核记录').disabled).toBe(false)
    expect(button('导出报告').disabled).toBe(false)
    authorize(false, ['delete', 'sensitive_export'])
    expect(button('新建审核').disabled).toBe(true)
    expect(button('重新审核').disabled).toBe(true)
    expect(button('删除审核记录').disabled).toBe(true)
    expect(button('导出报告').disabled).toBe(true)
    act(() => button('新建审核').click())
    expect(actions.createValidationReview).not.toHaveBeenCalled()
  } finally {
    act(() => root.unmount())
    client.clear()
    container.remove()
    document.body.replaceChildren()
  }
})
