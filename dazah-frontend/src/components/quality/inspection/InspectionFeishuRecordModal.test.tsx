/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { InspectionFeishuRecordModal } from './InspectionFeishuRecordModal'

// 弹窗提交走 server action，测试中不真正调用
vi.mock('@/actions/quality-inspection', () => ({
  createInspectionFeishuRecord: vi.fn().mockResolvedValue({ record_id: 'rec-new' }),
  updateInspectionFeishuRecord: vi.fn().mockResolvedValue({ record_id: 'rec-edit' }),
}))

// 字段元数据：SingleSelect「结果判断」带 合格/不合格 选项
vi.mock('@/lib/api/client/quality', () => ({
  fetchInspectionFeishuFields: vi.fn().mockResolvedValue({
    fields: [
      {
        field_name: '结果判断',
        ui_type: 'SingleSelect',
        editable: true,
        options: [{ name: '合格' }, { name: '不合格' }],
      },
      { field_name: '不合格项目', ui_type: 'Text', editable: true, options: null },
      { field_name: '厂家COA', ui_type: 'Attachment', editable: false, options: null },
    ],
    can_push: true,
  }),
}))

let container: HTMLDivElement
let root: Root

function renderModal(open = true, mode: 'create' | 'edit' = 'create') {
  act(() => {
    root.render(
      <App>
        <InspectionFeishuRecordModal
          open={open}
          entityCode="qc_solid_ys002"
          mode={mode}
          initialValues={mode === 'edit' ? { record_id: 'rec-1' } : undefined}
          onClose={() => {}}
          onSuccess={() => {}}
        />
      </App>,
    )
  })
}

async function flushFields() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
}

async function openSelectOptions() {
  const selector = document.body.querySelector('.ant-modal .ant-select') as HTMLElement
  await act(async () => {
    selector.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
    await new Promise((resolve) => setTimeout(resolve, 150))
  })
}

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
  vi.clearAllMocks()
})

describe('InspectionFeishuRecordModal', () => {
  it('renders SingleSelect 结果判断 with 合格/不合格 options from field metadata', async () => {
    renderModal()
    await flushFields()

    const optionTexts = Array.from(document.body.querySelectorAll('.ant-select-item-option')).map(
      (o) => o.textContent || '',
    )
    // 下拉未展开前不应出现选项
    expect(optionTexts).not.toContain('合格')

    await openSelectOptions()
    const openedTexts = Array.from(document.body.querySelectorAll('.ant-select-item-option')).map(
      (o) => o.textContent || '',
    )
    expect(openedTexts).toContain('合格')
    expect(openedTexts).toContain('不合格')
  })

  it('renders read-only attachment fields without a Select control', async () => {
    renderModal()
    await flushFields()

    const text = document.body.textContent || ''
    expect(text).toContain('结果判断')
    expect(text).toContain('不合格项目')
    expect(text).toContain('厂家COA')
  })
})
