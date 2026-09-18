/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  fetchInspectionFeishuFields: vi.fn(),
  createInspectionFeishuRecord: vi.fn(),
  updateInspectionFeishuRecord: vi.fn(),
}))

vi.mock('@/lib/api/client/quality', () => ({
  fetchInspectionFeishuFields: mocks.fetchInspectionFeishuFields,
}))

vi.mock('@/actions/quality-inspection', () => ({
  createInspectionFeishuRecord: mocks.createInspectionFeishuRecord,
  updateInspectionFeishuRecord: mocks.updateInspectionFeishuRecord,
}))

import { InspectionFeishuRecordModal } from './InspectionFeishuRecordModal'

const FIELDS = [
  { field_name: '器具名称', ui_type: 'Text', editable: true },
  { field_name: '检定日期', ui_type: 'DateTime', editable: true },
  { field_name: '附件', ui_type: 'Attachment', editable: false },
]

let container: HTMLDivElement
let root: Root

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  mocks.fetchInspectionFeishuFields.mockResolvedValue({
    fields: FIELDS,
    can_push: true,
    form_url: null,
  })
  mocks.createInspectionFeishuRecord.mockResolvedValue({ record_id: 'rec_new' })
  mocks.updateInspectionFeishuRecord.mockResolvedValue({ record_id: 'rec_old' })
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
  document.body.replaceChildren()
  vi.clearAllMocks()
})

function renderModal(
  mode: 'create' | 'edit',
  initialValues: Record<string, unknown>,
) {
  act(() => {
    root.render(
      <App>
        <InspectionFeishuRecordModal
          open
          entityCode="qc_instr_cal_external"
          mode={mode}
          initialValues={initialValues}
          onClose={vi.fn()}
          onSuccess={vi.fn()}
        />
      </App>,
    )
  })
}

async function waitFieldsLoaded() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 30))
  })
}

function clickSubmit() {
  const button = Array.from(document.querySelectorAll('button')).find(
    (node) => node.textContent === 'OK' || node.textContent === '确 定',
  )
  expect(button).toBeTruthy()
  return act(async () => {
    button!.click()
    await new Promise((resolve) => setTimeout(resolve, 20))
  })
}

describe('InspectionFeishuRecordModal 证书识别预填附件提交', () => {
  it('create 模式：只读附件预填值随表单一并提交', async () => {
    renderModal('create', {
      器具名称: '移液器',
      检定日期: '2026-08-13',
      附件: [{ file_token: 'ft_cert' }],
    })
    await waitFieldsLoaded()
    // 只读区展示附件预填提示
    expect(document.body.textContent).toContain('证书文件将随记录一并上传')

    await clickSubmit()
    expect(mocks.createInspectionFeishuRecord).toHaveBeenCalledTimes(1)
    const fields = mocks.createInspectionFeishuRecord.mock.calls[0]?.[1]
    expect(fields['器具名称']).toBe('移液器')
    expect(fields['附件']).toEqual([{ file_token: 'ft_cert' }])
  })

  it('edit 模式：只读附件不回写飞书', async () => {
    renderModal('edit', {
      record_id: 'rec_old',
      器具名称: '移液器',
      附件: [{ file_token: 'ft_cert' }],
    })
    await waitFieldsLoaded()

    await clickSubmit()
    expect(mocks.updateInspectionFeishuRecord).toHaveBeenCalledTimes(1)
    const [, , fields] = mocks.updateInspectionFeishuRecord.mock.calls[0]
    expect(fields).not.toHaveProperty('附件')
  })
})
