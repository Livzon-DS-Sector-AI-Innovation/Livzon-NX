/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const clientMocks = vi.hoisted(() => ({
  fetchFeishuMembers: vi.fn(),
}))

const actionMocks = vi.hoisted(() => ({
  createTrainingDeptMappingAction: vi.fn(),
  updateTrainingDeptMappingAction: vi.fn(),
  deleteTrainingDeptMappingAction: vi.fn(),
}))

vi.mock('@/lib/api/client/hr', () => ({ fetchFeishuMembers: clientMocks.fetchFeishuMembers }))
vi.mock('@/actions/hr', () => actionMocks)

import PersonDeptMappingClient from './PersonDeptMappingClient'

const PERSON_MAPPINGS = [
  {
    id: 'map-1',
    source_name: '赵双',
    target_name: '201二车间',
    mapping_type: 'person' as const,
    priority: 10,
    enabled: true,
    remark: null,
  },
]

function renderClient(element: React.ReactNode) {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root = createRoot(container)
  const settle = async () => {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 60))
    })
  }
  act(() => {
    root.render(
      <App>
        {element}
      </App>,
    )
  })
  return { container, root, settle }
}

describe('PersonDeptMappingClient', () => {
  let root: Root
  let container: HTMLElement

  beforeEach(() => {
    clientMocks.fetchFeishuMembers.mockResolvedValue({
      data: [{ name: '李四', department: '201二车间' }],
    })
    actionMocks.createTrainingDeptMappingAction.mockResolvedValue({ id: 'new-1' })
    actionMocks.updateTrainingDeptMappingAction.mockResolvedValue({ id: 'map-1' })
    actionMocks.deleteTrainingDeptMappingAction.mockResolvedValue({ id: 'map-1' })
  })

  afterEach(() => {
    act(() => root?.unmount())
    container?.remove()
    document.body
      .querySelectorAll('.ant-modal-root, .ant-select-dropdown, .ant-message, .ant-popover')
      .forEach((node) => node.remove())
    vi.clearAllMocks()
  })

  async function renderMappings(onChanged = vi.fn()) {
    const rendered = renderClient(
      <PersonDeptMappingClient
        mappings={PERSON_MAPPINGS as never}
        trainingDepts={['201二车间', '201二车间（DR）']}
        loading={false}
        onChanged={onChanged}
      />,
    )
    root = rendered.root
    container = rendered.container
    await rendered.settle()
    return onChanged
  }

  it('renders person mapping rows with name, target and switch', async () => {
    await renderMappings()
    const text = container.textContent || ''
    expect(text).toContain('赵双')
    expect(text).toContain('201二车间')
    expect(container.querySelector('.ant-switch')).toBeTruthy()
  })

  it('warns when batch saving without selecting people', async () => {
    await renderMappings()
    const button = Array.from(container.querySelectorAll('button')).find((btn) =>
      (btn.textContent || '').includes('批量配置'),
    )
    await act(async () => {
      button?.click()
      await new Promise((resolve) => setTimeout(resolve, 60))
    })
    expect(document.body.textContent).toContain('请先选择人员')
    expect(actionMocks.createTrainingDeptMappingAction).not.toHaveBeenCalled()
  })

  it('toggles a person mapping on and surfaces failure', async () => {
    const onChanged = await renderMappings()
    const sw = container.querySelector('.ant-switch') as HTMLElement | null
    await act(async () => {
      sw?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 60))
    })
    expect(actionMocks.updateTrainingDeptMappingAction).toHaveBeenCalledWith('map-1', {
      enabled: false,
    })
    expect(document.body.textContent).toContain('已停用')
    expect(onChanged).toHaveBeenCalled()

    actionMocks.updateTrainingDeptMappingAction.mockRejectedValue(new Error('无权限'))
    await act(async () => {
      sw?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 60))
    })
    expect(document.body.textContent).toContain('无权限')
  })

  it('opens the edit modal and saves a new target department', async () => {
    const onChanged = await renderMappings()
    const editButton = Array.from(container.querySelectorAll('.ant-table button')).find(
      (btn) => (btn.textContent || '').replace(/\s/g, '').includes('编辑'),
    )
    expect(editButton).toBeTruthy()
    await act(async () => {
      editButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 200))
    })
    expect(document.body.querySelector('.ant-modal-title')?.textContent).toContain(
      '编辑人员归属：赵双',
    )
    const saveButton = document.body.querySelector('.ant-modal-footer .ant-btn-primary')
    await act(async () => {
      saveButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 80))
    })
    expect(actionMocks.updateTrainingDeptMappingAction).toHaveBeenCalledWith(
      'map-1',
      expect.objectContaining({ target_name: '201二车间', remark: null }),
    )
    expect(document.body.textContent).toContain('已更新「赵双」的归属部门')
    expect(onChanged).toHaveBeenCalled()
  })

  it('deletes a person mapping after confirmation', async () => {
    const onChanged = await renderMappings()
    const deleteButton = Array.from(container.querySelectorAll('.ant-table button')).find(
      (btn) => (btn.textContent || '').replace(/\s/g, '').includes('删除'),
    )
    expect(deleteButton).toBeTruthy()
    await act(async () => {
      deleteButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 200))
    })
    // antd Popconfirm 确认按钮 portal 渲染到 body
    const confirmButton = document.body.querySelector(
      '.ant-popconfirm-buttons .ant-btn-primary',
    )
    expect(confirmButton).toBeTruthy()
    await act(async () => {
      confirmButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 120))
    })
    expect(actionMocks.deleteTrainingDeptMappingAction).toHaveBeenCalledWith('map-1')
    expect(onChanged).toHaveBeenCalled()
  })
})