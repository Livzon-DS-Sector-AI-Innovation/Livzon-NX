/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
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
      data: [{ id: 'p-1', name: '温度', value: '37', unit: '℃' }],
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
      root.render(<ParametersPage />)
    })

    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })

    const text = container.textContent || ''
    expect(text).toContain('工艺')
    expect(actions.getProcessSpecs).toHaveBeenCalled()
  })
})
