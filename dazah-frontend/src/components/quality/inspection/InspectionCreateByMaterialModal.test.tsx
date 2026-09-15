/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiClient = vi.hoisted(() => ({
  fetchInspectionMaterials: vi.fn(),
  fetchInspectionFeishuFields: vi.fn(),
}))

const inspectionActions = vi.hoisted(() => ({
  createInspectionFeishuRecord: vi.fn(),
}))

vi.mock('@/lib/api/client/quality', () => apiClient)
vi.mock('@/actions/quality-inspection', () => inspectionActions)

import { InspectionCreateByMaterialModal } from './InspectionCreateByMaterialModal'

const MATERIALS = [
  { entity_code: 'qc_solid_ys001', label: 'YS001 食用葡萄糖', module: 'solid', group_key: 'ys-000', group_label: 'YS000' },
  { entity_code: 'qc_solid_ys008', label: 'YS008 活性炭', module: 'solid', group_key: 'ys-000', group_label: 'YS000' },
  { entity_code: 'qc_solid_ys015', label: 'YS015 活性炭（303型湿）', module: 'solid', group_key: 'ys-100', group_label: 'YS100' },
  { entity_code: 'qc_liquid_yl001', label: 'YL001 乙醇', module: 'liquid', group_key: 'yl-0xx', group_label: 'YL0xx' },
]

const FIELDS = [
  { field_name: '批号', ui_type: 'Text', editable: true, options: null },
  { field_name: '物料代码', ui_type: 'Text', editable: true, options: null },
  { field_name: '物料名称', ui_type: 'Text', editable: true, options: null },
  { field_name: '结果判断', ui_type: 'SingleSelect', editable: true, options: [{ name: '合格' }, { name: '不合格' }] },
]

let container: HTMLDivElement
let root: Root

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  apiClient.fetchInspectionMaterials.mockResolvedValue(MATERIALS)
  apiClient.fetchInspectionFeishuFields.mockResolvedValue({ fields: FIELDS, can_push: true })
  inspectionActions.createInspectionFeishuRecord.mockResolvedValue({ record_id: 'rec-new' })
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
  document.body.replaceChildren()
  vi.clearAllMocks()
})

async function renderModal(onCreated = vi.fn(), props: Record<string, unknown> = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  act(() => {
    root.render(
      <QueryClientProvider client={queryClient}>
        <App>
          <InspectionCreateByMaterialModal open onClose={() => {}} onCreated={onCreated} {...props} />
        </App>
      </QueryClientProvider>,
    )
  })
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 30))
  })
  return onCreated
}

async function openMaterialSelect() {
  const selector = document.querySelector('.ant-modal .ant-select') as HTMLElement
  await act(async () => {
    selector.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
    await new Promise((resolve) => setTimeout(resolve, 150))
  })
}

function optionTexts(): string[] {
  return Array.from(document.querySelectorAll('.ant-select-item-option')).map(
    (o) => o.textContent || '',
  )
}

async function clickOption(text: string) {
  const option = Array.from(document.querySelectorAll('.ant-select-item-option')).find(
    (o) => o.textContent?.includes(text),
  )
  expect(option).toBeTruthy()
  await act(async () => {
    ;(option as HTMLElement).click()
    await new Promise((resolve) => setTimeout(resolve, 30))
  })
}

function findTextArea(placeholder: string): HTMLTextAreaElement | null {
  return Array.from(document.querySelectorAll('.ant-modal textarea')).find(
    (el) => (el as HTMLTextAreaElement).placeholder === placeholder,
  ) as HTMLTextAreaElement | null
}

function setTextAreaValue(el: HTMLTextAreaElement, value: string) {
  Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set?.call(
    el,
    value,
  )
  el.dispatchEvent(new Event('input', { bubbles: true }))
}

function findSubmitButton(): HTMLElement | null {
  // antd 对两个中文字的按钮会自动插入空格（如「提 交」），统一去除空白后匹配
  return Array.from(document.querySelectorAll('.ant-modal button')).find(
    (b) => (b.textContent ?? '').replace(/\s/g, '') === '提交',
  ) as HTMLElement | null
}

describe('InspectionCreateByMaterialModal 新增检验选料弹窗', () => {
  it('按名称模糊搜索展示全部固体+液体物料，同名多代码全部可选', async () => {
    await renderModal()

    await openMaterialSelect()
    const texts = optionTexts()
    expect(texts).toContain('YS001 食用葡萄糖')
    expect(texts).toContain('YS008 活性炭')
    expect(texts).toContain('YS015 活性炭（303型湿）')
    expect(texts).toContain('YL001 乙醇')
  })

  it('选择物料后展开该物料检验表并预填物料代码/名称，提交后 onCreated 收到跳转参数', async () => {
    const onCreated = await renderModal()

    await openMaterialSelect()
    await clickOption('YS001 食用葡萄糖')

    // 检验表字段展开，且物料代码/名称自动关联预填
    const codeInput = findTextArea('请输入物料代码')
    const nameInput = findTextArea('请输入物料名称')
    expect(codeInput).toBeTruthy()
    expect(nameInput).toBeTruthy()
    expect(codeInput?.value).toBe('YS001')
    expect(nameInput?.value).toBe('食用葡萄糖')

    // 填写批号后提交
    const batchInput = findTextArea('请输入批号')
    expect(batchInput).toBeTruthy()
    setTextAreaValue(batchInput as HTMLTextAreaElement, 'YS001-2609001')

    const submitButton = findSubmitButton()
    expect(submitButton).toBeTruthy()
    await act(async () => {
      ;(submitButton as HTMLElement).click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })

    expect(inspectionActions.createInspectionFeishuRecord).toHaveBeenCalledWith(
      'qc_solid_ys001',
      expect.objectContaining({
        物料代码: 'YS001',
        物料名称: '食用葡萄糖',
        批号: 'YS001-2609001',
      }),
    )
    expect(onCreated).toHaveBeenCalledWith({
      entityCode: 'qc_solid_ys001',
      recordId: 'rec-new',
      module: 'solid',
      groupKey: 'ys-000',
    })
  })

  it('同名物料对应多个代码时，选择不同代码后提交到对应物料实体', async () => {
    await renderModal()

    await openMaterialSelect()
    await clickOption('YS015 活性炭（303型湿）')

    const codeInput = findTextArea('请输入物料代码')
    expect(codeInput?.value).toBe('YS015')

    const submitButton = findSubmitButton()
    await act(async () => {
      ;(submitButton as HTMLElement).click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    expect(inspectionActions.createInspectionFeishuRecord).toHaveBeenCalledWith(
      'qc_solid_ys015',
      expect.objectContaining({ 物料代码: 'YS015' }),
    )
  })

  it('物料列表为空时展示空状态提示', async () => {
    apiClient.fetchInspectionMaterials.mockResolvedValue([])
    await renderModal()
    expect(document.body.textContent).toContain('暂无可用物料')
  })

  it('传入 module 时按模块过滤物料（固体页只列固体）', async () => {
    await renderModal(vi.fn(), { module: 'solid' })

    await openMaterialSelect()
    const texts = optionTexts()
    expect(texts).toContain('YS001 食用葡萄糖')
    expect(texts).toContain('YS008 活性炭')
    expect(texts).toContain('YS015 活性炭（303型湿）')
    expect(texts).not.toContain('YL001 乙醇')
  })
})
