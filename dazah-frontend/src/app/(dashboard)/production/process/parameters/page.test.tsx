/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const actions = vi.hoisted(() => ({
  getProcessSpecs: vi.fn(),
  getProcessSteps: vi.fn(),
  getProcessParameters: vi.fn(),
  createProcessParameter: vi.fn(),
  updateProcessParameter: vi.fn(),
  deleteProcessParameter: vi.fn(),
}))

vi.mock('@/actions/production', () => actions)

import ParametersPage from './page'

describe('ProcessParametersPage', () => {
  let root: ReturnType<typeof createRoot>
  let container: HTMLElement

  beforeEach(() => {
    actions.getProcessSpecs.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [{ id: 'spec-1', name: 'MC工艺规程', version: 'v1', status: 'effective' }],
    })
    actions.getProcessSteps.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [{ id: 'step-1', name: '发酵', spec_id: 'spec-1' }],
    })
    actions.getProcessParameters.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [{ id: 'p-1', param_name: '温度', param_code: 'TEMP', unit: '℃', min_value: 0, max_value: 100, is_critical: true }],
    })
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  it('renders process specs and steps', async () => {
    act(() => {
      root.render(<App><ParametersPage /></App>)
    })

    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })

    const text = container.textContent || ''
    expect(text).toContain('工艺')
    expect(actions.getProcessSpecs).toHaveBeenCalled()
  })

  it('renders spec/step selects and the empty state', async () => {
    act(() => {
      root.render(<App><ParametersPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('工艺参数管理')
    expect(text).toContain('选择工艺规程')
    expect(text).toContain('请先选择工艺规程和步骤')
    // 渲染两个 Select 下拉（工艺规程 + 工艺步骤）
    expect(container.querySelectorAll('.ant-select').length).toBe(2)
  })
})
