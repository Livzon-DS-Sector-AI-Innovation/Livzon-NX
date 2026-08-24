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
      data: [{ id: 'spec-1', spec_code: 'MC-01', spec_name: 'MC工艺规程', version: 'v1', status: 'effective' }],
    })
    actions.getProcessSteps.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [{ id: 'step-1', step_no: 1, step_name: '发酵', spec_id: 'spec-1' }],
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

  const flush = (ms: number) => new Promise((r) => setTimeout(r, ms))

  async function chooseOption(placeholder: string, optionText: string) {
    const sel = Array.from(document.querySelectorAll('.ant-select')).find((s) => (s.textContent || '').includes(placeholder))
    if (sel) {
      await act(async () => { sel.dispatchEvent(new MouseEvent('mousedown', { bubbles: true })); await flush(120) })
      const opts = Array.from(document.querySelectorAll('.ant-select-item-option'))
      const option = (opts.find((o) => (o.textContent || '').includes(optionText)) ?? opts[opts.length - 1]) as HTMLElement | null
      await act(async () => { option?.click(); await flush(120) })
    }
  }

  function setInputValue(el: HTMLInputElement, value: string) {
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set?.call(el, value)
    el.dispatchEvent(new Event('input', { bubbles: true }))
  }

  it('selects a spec and step, then renders parameters', async () => {
    act(() => {
      root.render(<App><ParametersPage /></App>)
    })
    await act(async () => { await flush(80) })
    await chooseOption('选择工艺规程', 'MC工艺规程')
    await chooseOption('选择工艺步骤', '发酵')
    await act(async () => { await flush(100) })
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('温度')
    expect(text).toContain('TEMP')
    expect(actions.getProcessSteps).toHaveBeenCalledWith('spec-1')
    expect(actions.getProcessParameters).toHaveBeenCalledWith('step-1')
  })

  it('creates a parameter through the modal', async () => {
    actions.createProcessParameter.mockResolvedValue({ code: 200, message: 'ok', data: null })
    act(() => {
      root.render(<App><ParametersPage /></App>)
    })
    await act(async () => { await flush(80) })
    await chooseOption('选择工艺规程', 'MC工艺规程')
    await chooseOption('选择工艺步骤', '发酵')
    await act(async () => { await flush(80) })
    expect((document.body.textContent || '')).toContain('温度')
    const addBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.replace(/\s/g, '') === '新建参数')
    await act(async () => { addBtn?.click(); await flush(120) })
    expect((document.body.textContent || '')).toContain('新建工艺参数')
    const paramInput = document.querySelector('.ant-modal input') as HTMLInputElement | null
    if (paramInput) {
      await act(async () => { setInputValue(paramInput, '进料温度'); await flush(40) })
    }
    const okBtn = document.querySelector('.ant-modal-footer .ant-btn-primary') as HTMLButtonElement | null
    await act(async () => { okBtn?.click(); await flush(180) })
    expect(actions.createProcessParameter).toHaveBeenCalledWith(expect.objectContaining({ param_name: '进料温度', step_id: 'step-1' }))
  })

  it('edits and updates a parameter', async () => {
    actions.updateProcessParameter.mockResolvedValue({ code: 200, message: 'ok', data: null })
    act(() => {
      root.render(<App><ParametersPage /></App>)
    })
    await act(async () => { await flush(80) })
    await chooseOption('选择工艺规程', 'MC工艺规程')
    await chooseOption('选择工艺步骤', '发酵')
    await act(async () => { await flush(80) })
    const editBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.replace(/\s/g, '') === '编辑')
    await act(async () => { editBtn?.click(); await flush(120) })
    expect((document.body.textContent || '')).toContain('编辑工艺参数')
    const okBtn = document.querySelector('.ant-modal-footer .ant-btn-primary') as HTMLButtonElement | null
    await act(async () => { okBtn?.click(); await flush(180) })
    expect(actions.updateProcessParameter).toHaveBeenCalledWith('p-1', expect.objectContaining({ param_name: '温度' }))
  })

  it('deletes a parameter after popconfirm approval', async () => {
    actions.deleteProcessParameter.mockResolvedValue({ code: 200, message: 'ok', data: null })
    act(() => {
      root.render(<App><ParametersPage /></App>)
    })
    await act(async () => { await flush(80) })
    await chooseOption('选择工艺规程', 'MC工艺规程')
    await chooseOption('选择工艺步骤', '发酵')
    await act(async () => { await flush(100) })
    const delBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.replace(/\s/g, '') === '删除')
    await act(async () => { delBtn?.click(); await flush(150) })
    const confirmOk = document.querySelector('.ant-popover .ant-btn-primary') as HTMLButtonElement | null
    if (confirmOk) {
      await act(async () => { confirmOk.click(); await flush(180) })
      expect(actions.deleteProcessParameter).toHaveBeenCalledWith('p-1')
    } else {
      expect(actions.deleteProcessParameter).toHaveBeenCalledWith('p-1')
    }
  })
})
