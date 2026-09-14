/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { InspectionFeishuRecordModal } from './InspectionFeishuRecordModal'

// 弹窗提交走 server action，测试中不真正调用
vi.mock('@/actions/quality-inspection', () => ({
  createInspectionFeishuRecord: vi.fn().mockResolvedValue({ record_id: 'rec-new' }),
  updateInspectionFeishuRecord: vi.fn().mockResolvedValue({ record_id: 'rec-edit' }),
}))

// 人员候选接口：FeishuPersonSelect 的目录来源
vi.mock('@/lib/api/client/quality', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api/client/quality')>()
  return {
    ...actual,
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
        // 人员字段：元数据标只读，但通用写接口支持按 [{id}] 提交
        { field_name: '使用负责人', ui_type: 'User', editable: false, options: null },
        // 主字段：新增记录必填
        {
          field_name: '生成日期',
          ui_type: 'DateTime',
          editable: true,
          is_primary: true,
          options: null,
        },
      ],
      can_push: true,
    }),
    fetchValidationPersonOptions: vi.fn().mockResolvedValue([
      { open_id: 'ou_dir_1', name: '李慧', department: 'QC', email: null, mobile: null },
    ]),
  }
})

let container: HTMLDivElement
let root: Root

interface ModalRenderOptions {
  mode?: 'create' | 'edit'
  editablePersonFields?: boolean
  initialValues?: Record<string, unknown>
}

function renderModal(options: ModalRenderOptions = {}) {
  const {
    mode = 'create',
    editablePersonFields = false,
    initialValues = mode === 'edit' ? { record_id: 'rec-1' } : undefined,
  } = options
  // 人员选择器内部用 useQuery 拉人事目录，需要自带 QueryClient
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  act(() => {
    root.render(
      <QueryClientProvider client={queryClient}>
        <App>
          <InspectionFeishuRecordModal
            open
            entityCode="qc_solid_ys002"
            mode={mode}
            initialValues={initialValues}
            editablePersonFields={editablePersonFields}
            onClose={() => {}}
            onSuccess={() => {}}
          />
        </App>
      </QueryClientProvider>,
    )
  })
}

async function flushFields() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0))
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

    // 人员字段默认只读：不出现在表单控件区，出现在只读说明区
    const text = document.body.textContent || ''
    expect(text).toContain('结果判断')
    expect(text).toContain('不合格项目')
    expect(text).toContain('厂家COA')
    expect(text).toContain('使用负责人')
  })

  it('renders User fields as person selector when editablePersonFields is on', async () => {
    renderModal({ editablePersonFields: true, initialValues: { record_id: 'rec-1' } })
    await flushFields()

    // 人员选择器渲染（带搜索输入），不再是纯只读文本
    const selects = document.body.querySelectorAll('.ant-modal .ant-select')
    expect(selects.length).toBeGreaterThan(0)
    // 人员选择器的占位文案（来自 FeishuPersonSelect）
    expect(document.body.textContent || '').toContain('输入姓名或拼音搜索人员')
    // 人员字段不再出现在只读说明区
    const readOnlyTitles = Array.from(
      document.body.querySelectorAll('.ant-modal .ant-descriptions'),
    ).map((node) => node.textContent || '')
    expect(
      readOnlyTitles.some((text) => text.includes('使用负责人')),
    ).toBe(false)
  })

  it('marks primary field as required via is_primary metadata', async () => {
    renderModal()
    await flushFields()

    const requiredLabels = Array.from(
      document.body.querySelectorAll('.ant-modal .ant-form-item-required'),
    ).map((node) => node.textContent || '')
    expect(requiredLabels).toContain('生成日期')
  })
})
