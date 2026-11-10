/* @vitest-environment happy-dom */
import { act, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { App, ConfigProvider, theme } from 'antd'
import { afterEach, expect, it, vi } from 'vitest'
import { createRoute, fetchOptimizations, fetchRoutes, updateRoute } from '@/lib/api/rd'
import type { CandidateRoute, ProcessOptimization, RouteDevelopment } from '@/types/rd'
import { ProcessOptimizationPage } from './process-optimization/ProcessOptimizationPage'
import { RouteDevelopmentPage } from './route-development/RouteDevelopmentPage'
import { ModuleResearch } from './route-development/ModuleResearch'
import { useWorkflowAutosave } from './useWorkflowAutosave'

vi.mock('@/lib/api/rd', () => ({
  fetchRoutes: vi.fn(), createRoute: vi.fn(), deleteRoute: vi.fn(), updateRoute: vi.fn(),
  fetchOptimizations: vi.fn(), createOptimization: vi.fn(), deleteOptimization: vi.fn(),
}))

vi.mock('./route-development/RouteWorkflowPage', () => ({
  RouteWorkflowPage: ({ routeId, literatureFile, onBack }: { routeId: string; literatureFile?: File; onBack: () => void }) =>
    <button onClick={() => {
      localStorage.setItem(`workflow-${routeId}`, JSON.stringify({ currentStep: 1, updatedAt: new Date().toISOString() }))
      onBack()
    }}>返回列表{literatureFile?.name}</button>,
}))

vi.mock('./process-optimization/ProcessOptimizationWorkflowPage', () => ({
  ProcessOptimizationWorkflowPage: ({ optimizationId, onBack }: { optimizationId: string; onBack: () => void }) =>
    <button onClick={() => {
      localStorage.setItem(`optimization-workflow-${optimizationId}`, JSON.stringify({ currentStep: 1, updatedAt: new Date().toISOString() }))
      onBack()
    }}>返回列表</button>,
}))

const record = {
  id: 'work-1', project_id: 'project-1', name: '研发工作流', status: 'in_progress',
  description: '', start_date: null, end_date: null, created_at: '', updated_at: '', created_by: null,
} as const
const route: RouteDevelopment = {
  ...record, route_no: 'RD-1', source: 'manual', source_reference: null, current_module: 'research',
  literature_sources: [], candidate_routes: [], selected_route_ids: [], experiment_plans: [], experiments: [], assessment: null, deliverables: [],
}
const optimization: ProcessOptimization = { ...record, optimization_no: 'OPT-1', current_module: 'doe' }

afterEach(() => {
  localStorage.clear()
  vi.useRealTimers()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

async function render(content: ReactNode, mode: string) {
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  await act(async () => root.render(<ConfigProvider theme={{ algorithm: mode === 'dark' ? theme.darkAlgorithm : theme.defaultAlgorithm }}>
    <App>{content}</App>
  </ConfigProvider>))
  return {
    host,
    button: (label: string) => Array.from(host.querySelectorAll('button')).find(button => button.textContent?.replace(/\s/g, '') === label),
    close: async () => { await act(async () => root.unmount()); host.remove() },
  }
}

it.each(['light', 'dark'])('refreshes both workflow lists and reads saved progress without a reload in %s mode', async mode => {
  const reload = vi.spyOn(window.location, 'reload').mockImplementation(() => {})
  let finishFirstRouteRequest: () => void = () => {}
  vi.mocked(fetchRoutes).mockReset().mockImplementationOnce(() => new Promise(resolve => {
    finishFirstRouteRequest = () => resolve({ items: [route], total: 1 })
  }))
    .mockResolvedValueOnce({ items: [{ ...route, name: '路线已更新' }], total: 1 })
  vi.mocked(fetchOptimizations).mockReset().mockResolvedValueOnce({ items: [optimization], total: 1, page: 1, page_size: 10 })
    .mockResolvedValueOnce({ items: [{ ...optimization, name: '优化已更新' }], total: 1, page: 1, page_size: 10 })
  for (const [content, api, title, finishEarlierRequest] of [
    [<RouteDevelopmentPage key="route" initialRoutes={[route]} initialTotal={1} />, fetchRoutes, '路线已更新', () => finishFirstRouteRequest()],
    [<ProcessOptimizationPage key="optimization" initialOptimizations={[optimization]} initialTotal={1} />, fetchOptimizations, '优化已更新', () => {}],
  ] as const) {
    const view = await render(content, mode)
    try {
      expect(view.button('开始')).toBeDefined()
      await act(async () => view.button('开始')?.click())
      await act(async () => view.button('返回列表')?.click())
      await act(async () => finishEarlierRequest())
      expect(view.host.textContent).toContain(title)
      expect(view.button('继续')).toBeDefined()
      expect(api).toHaveBeenCalledTimes(2)
    } finally {
      await view.close()
    }
  }
  expect(reload).not.toHaveBeenCalled()
})

it('replaces a failed literature file in the same workflow', async () => {
  const reload = vi.spyOn(window.location, 'reload').mockImplementation(() => {})
  const first = new File(['original'], 'original.pdf', { type: 'application/pdf' })
  const replacement = new File(['replacement'], 'replacement.pdf', { type: 'application/pdf' })
  const candidate: CandidateRoute = {
    id: 'candidate-1', name: '替换文献解析结果', is_recommended: true, steps: 1, total_yield: 80,
    starting_materials: [], key_step: '反应', advantages: [], risks: [],
  }
  const stream = 'data: ' + JSON.stringify({ status: 'complete', data: {
    candidate_routes: [candidate], experiment_plans: [],
  } }) + '\n'
  const fetcher = vi.fn().mockResolvedValueOnce(new Response(null, { status: 500 })).mockResolvedValueOnce(new Response(stream))
  vi.stubGlobal('fetch', fetcher)
  vi.mocked(updateRoute).mockResolvedValueOnce({ id: route.id, message: '已保存' })
  const view = await render(<ModuleResearch routeId={route.id} literatureFile={first} onComplete={vi.fn()} />, 'light')
  try {
    await vi.waitFor(() => expect(view.button('重新上传')).toBeDefined())
    const input = view.host.querySelector<HTMLInputElement>('input[type="file"]')!
    Object.defineProperty(input, 'files', { configurable: true, value: [replacement] })
    await act(async () => input.dispatchEvent(new Event('change', { bubbles: true })))
    await vi.waitFor(() => expect(view.host.textContent).toContain('替换文献解析结果'))
    expect(fetcher).toHaveBeenCalledTimes(2)
    expect(fetcher.mock.calls[1][1].body.get('file').name).toBe('replacement.pdf')
    expect(updateRoute).toHaveBeenCalledWith(route.id, expect.objectContaining({ selected_route_ids: ['candidate-1'] }))
    expect(createRoute).not.toHaveBeenCalled()
    expect(reload).not.toHaveBeenCalled()
  } finally {
    await view.close()
  }
})

it('saves the latest workflow state after an in-flight autosave before exiting', async () => {
  vi.useFakeTimers()
  let finishAutosave: () => void = () => {}
  const autosave = vi.fn(() => new Promise<void>(resolve => { finishAutosave = resolve }))
  const latest = vi.fn().mockResolvedValue(undefined)
  const exit = vi.fn()
  function Workflow() {
    const { runBeforeExit } = useWorkflowAutosave(autosave)
    return <button onClick={() => void runBeforeExit(latest, exit)}>保存并退出</button>
  }
  const view = await render(<Workflow />, 'light')
  try {
    await act(async () => vi.advanceTimersByTimeAsync(2000))
    expect(autosave).toHaveBeenCalledOnce()
    await act(async () => view.button('保存并退出')?.click())
    expect(latest).not.toHaveBeenCalled()
    expect(exit).not.toHaveBeenCalled()
    await act(async () => finishAutosave())
    expect(latest).toHaveBeenCalledOnce()
    expect(exit).toHaveBeenCalledOnce()
  } finally {
    await view.close()
  }
})
