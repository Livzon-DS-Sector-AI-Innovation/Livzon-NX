/* @vitest-environment happy-dom */
import { act, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, expect, it, vi } from 'vitest'
import { fetchRouteById, updateOptimization, updateRoute } from '@/lib/api/rd'
import type { CandidateRoute, ExperimentPlan } from '@/types/rd'
import { ProcessOptimizationWorkflowPage } from './process-optimization/ProcessOptimizationWorkflowPage'
import { RouteWorkflowPage } from './route-development/RouteWorkflowPage'

vi.mock('echarts-gl', () => ({}))
vi.mock('@/lib/api/rd', () => ({
  fetchRouteById: vi.fn(),
  updateOptimization: vi.fn(),
  updateRoute: vi.fn(),
}))

afterEach(() => {
  localStorage.clear()
  vi.resetAllMocks()
  vi.restoreAllMocks()
})

async function withWorkflow(content: ReactNode, check: (host: HTMLElement) => Promise<void>) {
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  try {
    await act(async () => root.render(<App>{content}</App>))
    await check(host)
  } finally {
    await act(async () => root.unmount())
    host.remove()
  }
}

async function saveAndExit(host: HTMLElement) {
  const save = Array.from(host.querySelectorAll('button')).find(button =>
    button.textContent?.replace(/\s/g, '').includes('保存并退出'),
  )
  if (!save) throw new Error('Missing workflow save and exit button')
  expect(save.disabled).toBe(false)
  await act(async () => save.click())
}

it('saves the selected literature route and its experiment plan before returning to the list', async () => {
  const chosen: CandidateRoute = {
    id: 'route-a', name: '路线甲', steps: 1, total_yield: 80, starting_materials: [],
    key_step: '反应', advantages: [], risks: [], is_recommended: true,
  }
  const alternate: CandidateRoute = { ...chosen, id: 'route-b', name: '路线乙', is_recommended: false }
  const plan: ExperimentPlan = {
    route_id: chosen.id, route_name: chosen.name, steps: [], analysis_methods: [],
    materials: [], equipment: [], safety_notes: [], estimated_duration: '1 天',
  }
  const draftKey = 'workflow-research-1'
  localStorage.setItem(draftKey, JSON.stringify({
    currentStep: 0, selectedRoutes: [chosen, alternate], selectedRouteIds: [chosen.id],
    experimentPlans: [plan], allExperiments: [], assessment: null,
  }))
  vi.mocked(fetchRouteById).mockResolvedValue(null)
  let finishSave: (() => void) | undefined
  vi.mocked(updateRoute).mockImplementation(() => new Promise(resolve => {
    finishSave = () => resolve({ id: 'research-1', message: '已保存' })
  }))
  const onBack = vi.fn(() => {
    expect(JSON.parse(localStorage.getItem(draftKey) ?? '{}')).toMatchObject({
      selectedRouteIds: [chosen.id], selectedRoutes: [chosen], experimentPlans: [plan],
    })
  })
  const onComplete = vi.fn()

  await withWorkflow(
    <RouteWorkflowPage routeId="research-1" routeName="文献路线" onBack={onBack} onComplete={onComplete} />,
    async host => {
      await saveAndExit(host)
      expect(updateRoute).toHaveBeenCalledExactlyOnceWith('research-1', expect.objectContaining({
        current_module: 'research', status: 'in_progress',
        selected_route_ids: [chosen.id], candidate_routes: [chosen], experiment_plans: [plan],
      }))
      expect(onBack).not.toHaveBeenCalled()
      await act(async () => finishSave?.())
      expect(onBack).toHaveBeenCalledOnce()
      expect(onComplete).not.toHaveBeenCalled()
    },
  )
})

it('keeps the optimization draft available when the server save fails', async () => {
  const onBack = vi.fn()
  const onComplete = vi.fn()
  vi.mocked(updateOptimization).mockRejectedValue(new Error('服务暂不可用'))
  const draftKey = 'optimization-workflow-opt-1'

  await withWorkflow(
    <ProcessOptimizationWorkflowPage optimizationId="opt-1" optimizationName="工艺条件优化"
      sourceRouteId="source-1" sourceRouteName="起始路线" onBack={onBack} onComplete={onComplete} />,
    async host => {
      await saveAndExit(host)
      expect(updateOptimization).toHaveBeenCalledExactlyOnceWith('opt-1', expect.objectContaining({
        current_module: 'doe', status: 'in_progress',
      }))
      expect(JSON.parse(localStorage.getItem(draftKey) ?? '{}')).toMatchObject({
        currentStep: 0, activeParallelTab: 'doe', optimizationName: '工艺条件优化',
        sourceRouteId: 'source-1', sourceRouteName: '起始路线',
      })
      expect(onBack).toHaveBeenCalledOnce()
      expect(onComplete).not.toHaveBeenCalled()
    },
  )
})
