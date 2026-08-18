/* @vitest-environment happy-dom */
/* eslint-disable @typescript-eslint/no-explicit-any, react/display-name */

import { act, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { renderToStaticMarkup } from 'react-dom/server'
import dayjs from 'dayjs'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const actions = vi.hoisted(() => ({
  approvePurchaseRequest: vi.fn(),
  rejectPurchaseRequest: vi.fn(),
  createPurchaseRequest: vi.fn(),
  deletePurchaseRequest: vi.fn(),
  submitPurchaseRequest: vi.fn(),
  updatePurchaseRequest: vi.fn(),
}))

const api = vi.hoisted(() => ({
  fetchPurchaseRequests: vi.fn(),
  fetchPurchaseOrders: vi.fn(),
  exportPurchaseOrdersExcel: vi.fn(),
  fetchMaterialOptions: vi.fn(),
}))

const ui = vi.hoisted(() => ({
  message: { error: vi.fn(), success: vi.fn() },
}))

vi.mock('@/actions/purchasing', () => actions)
vi.mock('@/lib/api/purchasing', () => api)

vi.mock('next/link', () => ({
  default: ({ href, children, ...props }: { href: string; children?: ReactNode }) =>
    <a href={href} {...props}>{children}</a>,
}))

vi.mock('antd', async () => {
  const React = await import('react')
  type AnyProps = Record<string, any>

  const createForm = () => {
    const form: AnyProps = {
      initialized: false,
      values: {
        request_date: dayjs('2026-08-12'),
        attachment_note: '',
        items: [],
        groups: [],
      },
    }
    form.getFieldValue = (name: string | number | Array<string | number>) => {
      const path = Array.isArray(name) ? name : [name]
      return path.reduce((value: unknown, key) => (
        value == null ? undefined : (value as AnyProps)[key]
      ), form.values)
    }
    form.setFieldsValue = (values: AnyProps) => {
      form.values = { ...form.values, ...values }
    }
    form.setFieldValue = (name: string | Array<string | number>, value: unknown) => {
      const path = Array.isArray(name) ? name : [name]
      let target = form.values
      for (const key of path.slice(0, -1)) {
        target[key] ??= {}
        target = target[key]
      }
      target[path[path.length - 1]] = value
    }
    form.resetFields = () => {
      form.values = {
        request_date: dayjs('2026-08-12'),
        attachment_note: '',
        items: [],
        groups: [],
      }
    }
    form.validateFields = async () => form.values
    return form
  }

  const App = {
    useApp: () => ({ message: ui.message }),
  }

  const Button = ({ children, htmlType, onClick, disabled, loading, ...props }: AnyProps) => (
    <button
      type={htmlType === 'submit' ? 'submit' : 'button'}
      disabled={disabled || loading}
      onClick={onClick}
      {...props}
    >
      {children}
    </button>
  )

  const Input = (props: AnyProps) => <input {...props} />
  Input.TextArea = ({ onChange, ...props }: AnyProps) => (
    <textarea {...props} onInput={onChange} onChange={onChange} />
  )

  const InputNumber = (props: AnyProps) => <input type="number" {...props} />
  const AutoComplete = ({ value, onChange, ...props }: AnyProps) => (
    <input
      {...props}
      value={value ?? ''}
      onChange={(event) => onChange?.(event.target.value)}
    />
  )
  const DatePicker = ({ value, onChange, ...props }: AnyProps) => (
    <input
      {...props}
      value={value?.format?.('YYYY-MM-DD') ?? ''}
      onChange={(event) => onChange?.(dayjs(event.target.value))}
    />
  )

  const Select = ({ options = [], value, onChange, ...props }: AnyProps) => (
    <select
      {...props}
      value={value ?? ''}
      onChange={(event) => onChange?.(event.target.value)}
    >
      {options.map((option: AnyProps) => (
        <option key={String(option.value)} value={option.value} disabled={option.disabled}>
          {option.label}
        </option>
      ))}
    </select>
  )

  const Segmented = ({ options = [], value, onChange }: AnyProps) => (
    <select value={value} onChange={(event) => onChange?.(event.target.value)}>
      {options.map((option: AnyProps) => (
        <option key={String(option.value)} value={option.value}>{option.label}</option>
      ))}
    </select>
  )

  const Space = ({ children }: AnyProps) => <span>{children}</span>
  const Upload = ({ children, ...props }: AnyProps) => (
    <span {...props}>{children}</span>
  )
  const Tag = ({ children }: AnyProps) => <span>{children}</span>
  const Alert = ({ message, description, action, ...props }: AnyProps) => (
    <div role="alert" {...props}>
      <strong>{message}</strong>
      <span>{description}</span>
      {action}
    </div>
  )

  const Descriptions = ({ children }: AnyProps) => <dl>{children}</dl>
  Descriptions.Item = ({ label, children }: AnyProps) => (
    <div><dt>{label}</dt><dd>{children}</dd></div>
  )

  const Modal = ({ open, title, children, onOk, onCancel, okText, cancelText }: AnyProps) => {
    if (!open) return null
    return (
      <div role="dialog">
        <h2>{title}</h2>
        <div>{children}</div>
        {onOk && <button type="button" onClick={onOk}>{okText ?? '确定'}</button>}
        {onCancel && <button type="button" onClick={onCancel}>{cancelText ?? '取消'}</button>}
      </div>
    )
  }

  const Popconfirm = ({ children, onConfirm, okText }: AnyProps) => (
    <span>
      {children}
      <button type="button" data-confirm="true" onClick={onConfirm}>{okText ?? '确定'}</button>
    </span>
  )

  const Form = ({ form, initialValues, onFinish, children }: AnyProps) => {
    ;(globalThis as AnyProps).__dazahActiveForm = form
    if (!form.initialized) {
      form.values = { ...form.values, ...(initialValues ?? {}) }
      form.initialized = true
    }
    return (
      <form
        onSubmit={(event) => {
          event.preventDefault()
          void onFinish?.(form.values)
        }}
      >
        {children}
      </form>
    )
  }
  Form.useForm = () => {
    const [form] = React.useState(createForm)
    return [form]
  }
  Form.useWatch = (name: string, form: AnyProps) => form?.getFieldValue(name)
  Form.Item = ({ children }: AnyProps) => (
    <>{typeof children === 'function' ? children() : children}</>
  )
  Form.List = ({ name, children }: AnyProps) => {
    const activeForm = (globalThis as AnyProps).__dazahActiveForm as AnyProps | undefined
    const form = activeForm
    const path = Array.isArray(name) ? name : [name]
    const resolvedPath = path.length > 1 && typeof path[0] === 'number'
      ? ['groups', ...path]
      : path
    let values = form?.getFieldValue(path) as unknown
    if (resolvedPath !== path) values = form?.getFieldValue(resolvedPath) as unknown
    if (!Array.isArray(values)) values = []
    const updateList = (nextValues: unknown[]) => {
      if (!form) return
      if (resolvedPath.length === 1) {
        form.values[resolvedPath[0]] = nextValues
        return
      }
      let target = form.values
      for (const key of resolvedPath.slice(0, -1)) {
        target[key] ??= {}
        target = target[key]
      }
      target[resolvedPath[resolvedPath.length - 1]] = nextValues
    }
    const fields = (values as unknown[]).map((_, index) => ({ key: index, name: index }))
    return children(fields, {
      add: (value: unknown) => updateList([...(values as unknown[]), value]),
      remove: (index: number) => updateList((values as unknown[]).filter((_, i) => i !== index)),
    })
  }

  const Table = ({ columns = [], dataSource = [], summary }: AnyProps) => {
    const rows = dataSource as AnyProps[]
    const cells = rows.flatMap((row, rowIndex) => columns.map((column: AnyProps, columnIndex: number) => (
      <span key={`${rowIndex}-${columnIndex}`}>
        {column.title}
        {typeof column.render === 'function'
          ? column.render(column.dataIndex ? row[column.dataIndex] : undefined, row, rowIndex)
          : column.dataIndex ? row[column.dataIndex] : column.title}
      </span>
    )))
    return (
      <div data-table="true">
        {cells}
        {summary?.()}
      </div>
    )
  }
  Table.Summary = {
    Row: ({ children }: AnyProps) => <div>{children}</div>,
    Cell: ({ children }: AnyProps) => <span>{children}</span>,
  }

  return {
    App,
    Alert,
    AutoComplete,
    Button,
    DatePicker,
    Descriptions,
    Form,
    Input,
    InputNumber,
    Modal,
    Popconfirm,
    Select,
    Segmented,
    Space,
    Table,
    Tag,
    Upload,
  }
})

import { PurchaseApprovalClient } from './PurchaseApprovalClient'
import { PurchaseOrderClient } from './PurchaseOrderClient'
import { PurchaseRequestFormClient } from './PurchaseRequestFormClient'
import { PurchasingWorkspaceClient } from './PurchasingWorkspaceClient'
import {
  buildUrgentPurchasePayload,
  itemDetailColumns,
  normalizeGroups,
} from './UrgentPurchaseRequestFormClient'

const item = {
  id: '33333333-3333-3333-3333-333333333333',
  sequence: 1,
  item_category: 'hardware',
  product_name: '标签纸',
  specification: 'A4',
  material_code: 'HW-001',
  material_description: '钢制件',
  rule_model: 'M1',
  purpose: '生产使用',
  material: '钢',
  brand: '品牌A',
  quantity: '2',
  unit: '件',
  unit_price: '5.00',
  total_amount: '10.00',
  remarks: '急用',
}

const request = (overrides: Record<string, unknown> = {}) => ({
  id: '22222222-2222-2222-2222-222222222222',
  category: 'hardware',
  request_department: '工程设备部',
  request_date: '2026-08-12',
  attachment_note: '技术附件',
  total_amount: '10.00',
  status: 'draft',
  items: [item],
  approvals: [
    {
      id: '44444444-4444-4444-4444-444444444444',
      approval_role: 'department_head',
      result: 'approved',
      approver_name: '张三',
      opinion: '同意',
      approval_time: '2026-08-12T10:00:00Z',
    },
  ],
  ...overrides,
}) as any

const orderLine = {
  item_id: item.id,
  item_sequence: 1,
  request_id: request().id,
  request_date: '2026-08-12',
  request_department: '工程设备部',
  category: 'hardware',
  category_label: '五金材料',
  item_category: 'hardware',
  product_name: '标签纸',
  specification: 'A4',
  material_code: 'HW-001',
  material_description: '钢制件',
  rule_model: 'M1',
  purpose: '生产使用',
  material: '钢',
  brand: '品牌A',
  quantity: '2',
  unit: '件',
  unit_price: '5.00',
  total_amount: '10.00',
  remarks: '急用',
} as any

let container: HTMLDivElement
let root: Root

function mount(element: ReactNode) {
  container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
  act(() => root.render(element))
  return container
}

function buttonContaining(text: string, occurrence = 0) {
  return Array.from(container.querySelectorAll('button')).filter((button) =>
    button.textContent?.includes(text)
  )[occurrence]
}

async function flush() {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  actions.approvePurchaseRequest.mockResolvedValue({ code: 200, message: 'success', data: {} })
  actions.rejectPurchaseRequest.mockResolvedValue({ code: 200, message: 'success', data: {} })
  actions.createPurchaseRequest.mockResolvedValue({ code: 200, message: 'success', data: request() })
  actions.deletePurchaseRequest.mockResolvedValue({ code: 200, message: 'success', data: { success_count: 1, fail_count: 0 } })
  actions.submitPurchaseRequest.mockResolvedValue({ code: 200, message: 'success', data: request() })
  actions.updatePurchaseRequest.mockResolvedValue({ code: 200, message: 'success', data: request() })
  api.fetchPurchaseRequests.mockResolvedValue({ code: 200, message: 'success', data: [request()], meta: { total: 1 } })
  api.fetchPurchaseOrders.mockResolvedValue({ code: 200, message: 'success', data: [orderLine], meta: { total: 1 } })
  api.exportPurchaseOrdersExcel.mockResolvedValue({ blob: new Blob(['xlsx']), filename: '采购订单.xlsx' })
  window.scrollTo = vi.fn()
  ;(globalThis as any).__dazahActiveForm = undefined
})

afterEach(() => {
  act(() => root?.unmount())
  container?.remove()
  delete (globalThis as any).__dazahActiveForm
})

describe('purchasing workspace and request forms', () => {
  it('renders the workflow workspace and all request entry categories', () => {
    const markup = renderToStaticMarkup(<PurchasingWorkspaceClient />)
    expect(markup).toContain('采购管理工作台')
    expect(markup).toContain('加急采购申请')
    expect(markup).toContain('加急单')
    expect(markup).toContain('部门负责人')
  })

  it('normalizes urgent groups and trims payload fields', () => {
    expect(itemDetailColumns(false, 'hardware')).toHaveLength(4)
    expect(itemDetailColumns(false, 'office')).toHaveLength(3)
    const normalized = normalizeGroups(request({
      category: 'urgent',
      items: [item, { ...item, id: '55555555-5555-5555-5555-555555555555', item_category: 'urgent' }, { ...item, item_category: undefined }],
    }))
    expect(normalized).toHaveLength(1)
    expect(normalized[0].category).toBe('hardware')

    const payload = buildUrgentPurchasePayload({
      request_department: '  采购部  ',
      request_date: dayjs('2026-08-12'),
      attachment_note: '  说明  ',
      groups: [{
        category: 'hardware',
        items: [{
          product_name: '  标签纸 ', specification: ' A4 ', material_code: ' HW-1 ',
          material_description: ' 纸 ', rule_model: ' M1 ', purpose: ' 生产 ',
          material: ' 纸 ', brand: ' A ', quantity: 1, unit: ' 包 ', unit_price: 2,
          remarks: ' 急用 ',
        }],
      }],
    })
    expect(payload).toMatchObject({ category: 'urgent', request_department: '采购部', attachment_note: '说明' })
    expect(payload.items[0]).toMatchObject({ item_category: 'hardware', product_name: '标签纸', unit: '包' })
  })

  it('covers standard request attachment, material columns, save, edit, detail, and submit flows', async () => {
    mount(
      <PurchaseRequestFormClient
        category="hardware"
        categoryLabel="五金材料"
        initialRequests={[request()]}
        initialTotal={1}
      />,
    )

    expect(container.textContent).toContain('五金材料采购申请')
    act(() => buttonContaining('附件说明')?.click())
    expect(container.querySelector('[role="dialog"]')?.textContent).toContain('附件说明')
    const noteEditor = container.querySelector('textarea') as HTMLTextAreaElement
    act(() => {
      noteEditor.value = '  申请附件  '
      noteEditor.dispatchEvent(new Event('input', { bubbles: true }))
    })
    act(() => buttonContaining('保存说明')?.click())
    act(() => buttonContaining('附件说明')?.click())
    act(() => buttonContaining('取消')?.click())

    await act(async () => buttonContaining('保存申请')?.click())
    await flush()
    expect(actions.createPurchaseRequest).toHaveBeenCalledWith(expect.objectContaining({
      category: 'hardware',
      attachment_note: '申请附件',
    }))
    expect(api.fetchPurchaseRequests).toHaveBeenCalled()

    act(() => buttonContaining('查看')?.click())
    expect(container.querySelector('[role="dialog"]')?.textContent).toContain('技术附件')
    act(() => buttonContaining('取消')?.click())

    act(() => buttonContaining('编辑')?.click())
    expect(container.textContent).toContain('更新申请')
    await act(async () => buttonContaining('更新申请')?.click())
    await flush()
    expect(actions.updatePurchaseRequest).toHaveBeenCalledWith(
      request().id,
      expect.objectContaining({ attachment_note: '技术附件' }),
    )

    await act(async () => {
      const confirmButtons = Array.from(container.querySelectorAll<HTMLButtonElement>('button[data-confirm="true"]'))
      confirmButtons[0]?.click()
    })
    await flush()
    expect(actions.submitPurchaseRequest).toHaveBeenCalledWith(request().id)
  })

  it('renders the non-material standard form branch', () => {
    mount(
      <PurchaseRequestFormClient
        category="office"
        categoryLabel="办公用品"
        initialRequests={[request({ category: 'office', items: [{ ...item, item_category: undefined }] })]}
        initialTotal={1}
      />,
    )
    expect(container.textContent).toContain('办公用品采购申请')
    expect(container.textContent).toContain('商品名称')
    expect(container.textContent).toContain('规格')
  })

  it('covers urgent category selection, both item column branches, save, edit, and submit flows', async () => {
    mount(
      <PurchaseRequestFormClient
        category="urgent"
        categoryLabel="加急单"
        initialRequests={[request({ category: 'urgent', status: 'rejected' })]}
        initialTotal={1}
      />,
    )

    act(() => buttonContaining('添加申请类型')?.click())
    expect(container.querySelector('[role="dialog"]')).not.toBeNull()
    const picker = container.querySelector('select') as HTMLSelectElement
    act(() => {
      picker.value = 'hardware'
      picker.dispatchEvent(new Event('change', { bubbles: true }))
    })
    act(() => Array.from(container.querySelectorAll('button')).find((button) => button.textContent === '添加')?.click())
    expect(container.textContent).toContain('五金材料')

    act(() => buttonContaining('添加申请类型')?.click())
    const officePicker = container.querySelector('select') as HTMLSelectElement
    act(() => {
      officePicker.value = 'office'
      officePicker.dispatchEvent(new Event('change', { bubbles: true }))
    })
    act(() => Array.from(container.querySelectorAll('button')).find((button) => button.textContent === '添加')?.click())
    expect(container.textContent).toContain('办公用品')

    act(() => buttonContaining('附件说明')?.click())
    const urgentNoteEditor = container.querySelector('textarea') as HTMLTextAreaElement
    act(() => {
      urgentNoteEditor.value = '加急附件'
      urgentNoteEditor.dispatchEvent(new Event('input', { bubbles: true }))
    })
    act(() => buttonContaining('保存说明')?.click())
    await act(async () => buttonContaining('保存申请')?.click())
    await flush()
    expect(actions.createPurchaseRequest).toHaveBeenCalledWith(expect.objectContaining({ category: 'urgent' }))

    act(() => buttonContaining('查看')?.click())
    expect(container.querySelector('[role="dialog"]')?.textContent).toContain('物料编码/商品名称')
    act(() => buttonContaining('取消')?.click())

    act(() => buttonContaining('编辑')?.click())
    expect(container.textContent).toContain('更新申请')
    await act(async () => buttonContaining('更新申请')?.click())
    await flush()
    expect(actions.updatePurchaseRequest).toHaveBeenCalled()

    await act(async () => {
      const confirms = Array.from(container.querySelectorAll<HTMLButtonElement>('button[data-confirm="true"]'))
      confirms[0]?.click()
    })
    await flush()
    expect(actions.submitPurchaseRequest).toHaveBeenCalled()
  })

  it('auto-calculates urgent line totals, group subtotals, and the grand total', () => {
    mount(
      <PurchaseRequestFormClient
        category="urgent"
        categoryLabel="加急单"
        initialRequests={[]}
        initialTotal={0}
      />,
    )

    act(() => buttonContaining('添加申请类型')?.click())
    const picker = container.querySelector('select') as HTMLSelectElement
    act(() => {
      picker.value = 'hardware'
      picker.dispatchEvent(new Event('change', { bubbles: true }))
    })
    act(() => Array.from(container.querySelectorAll('button')).find((button) => button.textContent === '添加')?.click())
    act(() => buttonContaining('新增明细')?.click())

    const activeForm = (globalThis as any).__dazahActiveForm
    act(() => {
      activeForm.values.groups[0].items[0].quantity = 2
      activeForm.values.groups[0].items[0].unit_price = 5
      activeForm.values.groups[0].items[1].quantity = 3
      activeForm.values.groups[0].items[1].unit_price = 5
    })
    // 触发一次重渲染，让总额、分组小计、合计重新读取表单值
    act(() => buttonContaining('附件说明')?.click())
    act(() => buttonContaining('取消')?.click())

    expect(container.textContent).toContain('¥10.00')
    expect(container.textContent).toContain('¥15.00')
    expect(container.textContent).toContain('分组小计')
    expect(container.textContent).toContain('合计：¥25.00')
  })

  it('auto-fills urgent material description and rule model from the material code', async () => {
    api.fetchMaterialOptions.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [{
        record_id: 'rec-1',
        material_code: 'MAT-001',
        material_description: '不锈钢管',
        rule_model: 'DN50',
        material_unit: '米',
      }],
    })

    mount(
      <PurchaseRequestFormClient
        category="urgent"
        categoryLabel="加急单"
        initialRequests={[]}
        initialTotal={0}
      />,
    )

    act(() => buttonContaining('添加申请类型')?.click())
    const picker = container.querySelector('select') as HTMLSelectElement
    act(() => {
      picker.value = 'hardware'
      picker.dispatchEvent(new Event('change', { bubbles: true }))
    })
    act(() => Array.from(container.querySelectorAll('button')).find((button) => button.textContent === '添加')?.click())

    const materialCodeInput = container.querySelector('input[placeholder="输入物料编码联想"]') as HTMLInputElement
    const nativeValueSetter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      'value',
    )?.set
    act(() => {
      nativeValueSetter?.call(materialCodeInput, 'MAT-001')
      materialCodeInput.dispatchEvent(new Event('input', { bubbles: true }))
    })
    // 等待联想防抖与远端匹配完成，物料说明和规格型号应自动填入
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 400))
    })

    // mock 的 Form.Item 不绑定值，物料编码经输入框受控状态保留，
    // 自动填入的物料说明与规格型号写入表单后随保存 payload 提交
    expect(materialCodeInput.value).toBe('MAT-001')
    await act(async () => buttonContaining('保存申请')?.click())
    await flush()
    expect(actions.createPurchaseRequest).toHaveBeenCalledWith(expect.objectContaining({
      category: 'urgent',
      items: [expect.objectContaining({
        material_description: '不锈钢管',
        rule_model: 'DN50',
      })],
    }))
  })

  it('reports urgent form, list, and submit errors', async () => {
    mount(
      <PurchaseRequestFormClient
        category="urgent"
        categoryLabel="加急单"
        initialRequests={[request({ category: 'urgent', status: 'rejected' })]}
        initialTotal={1}
      />,
    )

    await act(async () => buttonContaining('保存申请')?.click())
    await flush()
    expect(ui.message.error).toHaveBeenCalledWith('加急单至少需要添加一个申请类型和一条明细')

    const addCategory = (category: string) => {
      act(() => buttonContaining('添加申请类型')?.click())
      const picker = container.querySelector('select') as HTMLSelectElement
      act(() => {
        picker.value = category
        picker.dispatchEvent(new Event('change', { bubbles: true }))
      })
      act(() => Array.from(container.querySelectorAll('button')).find((button) => button.textContent === '添加')?.click())
    }
    addCategory('hardware')
    act(() => buttonContaining('新增明细')?.click())

    actions.createPurchaseRequest.mockResolvedValueOnce({ code: 400, message: '保存失败' })
    await act(async () => buttonContaining('保存申请')?.click())
    await flush()
    expect(ui.message.error).toHaveBeenCalledWith('保存失败')

    actions.createPurchaseRequest.mockRejectedValueOnce(new Error('provider'))
    await act(async () => buttonContaining('保存申请')?.click())
    await flush()
    expect(ui.message.error).toHaveBeenCalledWith('采购申请保存失败，请稍后重试')

    actions.submitPurchaseRequest.mockResolvedValueOnce({ code: 400, message: '提交失败' })
    await act(async () => {
      const confirms = Array.from(container.querySelectorAll<HTMLButtonElement>('button[data-confirm="true"]'))
      confirms.at(-1)?.click()
    })
    await flush()
    expect(ui.message.error).toHaveBeenCalledWith('提交失败')

    actions.submitPurchaseRequest.mockRejectedValueOnce(new Error('provider'))
    await act(async () => {
      const confirms = Array.from(container.querySelectorAll<HTMLButtonElement>('button[data-confirm="true"]'))
      confirms.at(-1)?.click()
    })
    await flush()
    expect(ui.message.error).toHaveBeenCalledWith('采购申请提交失败，请稍后重试')

    api.fetchPurchaseRequests.mockRejectedValueOnce(new Error('network'))
    await act(async () => buttonContaining('刷新')?.click())
    await flush()
    expect(ui.message.error).toHaveBeenCalledWith('采购申请列表加载失败')

    act(() => buttonContaining('添加申请类型')?.click())
    act(() => buttonContaining('取消')?.click())
    act(() => buttonContaining('删除类型')?.click())
    const groupDelete = Array.from(container.querySelectorAll<HTMLButtonElement>('button[data-confirm="true"]')).find(
      (button) => button.textContent === '删除',
    )
    act(() => groupDelete?.click())
  })

  it('shows retry feedback when the urgent request list failed initially', async () => {
    mount(
      <PurchaseRequestFormClient
        category="urgent"
        categoryLabel="加急单"
        initialRequests={[]}
        initialTotal={0}
        initialLoadFailed
      />,
    )

    expect(container.querySelector('[role="alert"]')?.textContent).toContain('加急申请记录加载失败')
    await act(async () => buttonContaining('重试')?.click())
    await flush()
    expect(api.fetchPurchaseRequests).toHaveBeenCalled()
    expect(container.querySelector('[role="alert"]')).toBeNull()
  })
})

describe('purchasing approval and order clients', () => {
  it('covers co-sign approval, urgent-compatible detail columns, view changes, and refresh errors', async () => {
    const approvalRequest = request({
      category: 'electrical',
      status: 'pending_equipment_power',
      attachment_note: '会签附件',
      items: [{ ...item, item_category: 'hardware', material_code: 'M-1' }],
    })
    api.fetchPurchaseRequests.mockResolvedValue({ code: 200, message: 'success', data: [approvalRequest], meta: { total: 1 } })
    actions.approvePurchaseRequest.mockResolvedValue({
      code: 200,
      message: 'success',
      data: { status: 'pending_equipment_power' },
    })
    mount(
      <PurchaseApprovalClient
        category="electrical"
        categoryLabel="电气"
        approvalRole="equipment_power"
        initialRequests={[approvalRequest]}
        initialTotal={1}
      />,
    )

    const viewSelect = container.querySelector('select') as HTMLSelectElement
    act(() => {
      viewSelect.value = 'completed'
      viewSelect.dispatchEvent(new Event('change', { bubbles: true }))
    })
    await flush()
    expect(api.fetchPurchaseRequests).toHaveBeenCalledWith(expect.objectContaining({
      approval_role: 'equipment_power',
      approval_view: 'completed',
    }))

    act(() => {
      viewSelect.value = 'pending'
      viewSelect.dispatchEvent(new Event('change', { bubbles: true }))
    })
    await flush()

    act(() => buttonContaining('查看')?.click())
    expect(container.querySelector('[role="dialog"]')?.textContent).toContain('会签附件')
    act(() => buttonContaining('取消')?.click())

    act(() => buttonContaining('通过')?.click())
    expect(container.querySelector('[role="dialog"]')?.textContent).toContain('何学斌')
    await act(async () => buttonContaining('确认通过')?.click())
    await flush()
    expect(actions.approvePurchaseRequest).toHaveBeenCalledWith(
      approvalRequest.id,
      expect.objectContaining({ approval_role: 'equipment_power', result: 'approved' }),
    )
    expect(ui.message.success).toHaveBeenCalledWith('已记录一名设备动力部会签，等待另一名审批人')

    api.fetchPurchaseRequests.mockRejectedValueOnce(new Error('network'))
    await act(async () => buttonContaining('刷新')?.click())
    await flush()
    expect(ui.message.error).toHaveBeenCalledWith('待审批列表加载失败')
  })

  it('covers regular rejection success and provider failures', async () => {
    const approvalRequest = request({ status: 'pending_department_head' })
    mount(
      <PurchaseApprovalClient
        category="urgent"
        categoryLabel="加急单"
        approvalRole="department_head"
        initialRequests={[approvalRequest]}
        initialTotal={1}
      />,
    )

    act(() => buttonContaining('查看')?.click())
    expect(container.querySelector('[role="dialog"]')?.textContent).toContain('物料编码/商品名称')
    act(() => buttonContaining('取消')?.click())

    act(() => buttonContaining('驳回')?.click())
    await act(async () => buttonContaining('确认驳回')?.click())
    await flush()
    expect(actions.rejectPurchaseRequest).toHaveBeenCalledWith(
      approvalRequest.id,
      expect.objectContaining({ result: 'rejected', opinion: '' }),
    )
    expect(ui.message.success).toHaveBeenCalledWith('审批已驳回')

    actions.rejectPurchaseRequest.mockRejectedValueOnce(new Error('provider'))
    act(() => buttonContaining('驳回')?.click())
    await act(async () => buttonContaining('确认驳回')?.click())
    await flush()
    expect(ui.message.error).toHaveBeenCalledWith('审批失败，请稍后重试')
  })

  it('covers order filters, all column layouts, export, search, and errors', async () => {
    const createObjectURL = vi.fn(() => 'blob:purchase-orders')
    const revokeObjectURL = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectURL })

    mount(
      <PurchaseOrderClient
        initialLines={[orderLine]}
        initialTotal={1}
        initialYear={2026}
        initialMonth={8}
      />,
    )

    const categorySelect = container.querySelector('select') as HTMLSelectElement
    act(() => {
      categorySelect.value = 'urgent'
      categorySelect.dispatchEvent(new Event('change', { bubbles: true }))
    })
    act(() => {
      categorySelect.value = 'hardware'
      categorySelect.dispatchEvent(new Event('change', { bubbles: true }))
    })
    act(() => {
      categorySelect.value = 'office'
      categorySelect.dispatchEvent(new Event('change', { bubbles: true }))
    })
    act(() => {
      categorySelect.value = 'all'
      categorySelect.dispatchEvent(new Event('change', { bubbles: true }))
    })
    await act(async () => buttonContaining('查询')?.click())
    await flush()
    await act(async () => buttonContaining('导出 Excel')?.click())
    await flush()
    expect(api.fetchPurchaseOrders).toHaveBeenCalled()
    expect(api.exportPurchaseOrdersExcel).toHaveBeenCalled()
    expect(createObjectURL).toHaveBeenCalled()
    expect(revokeObjectURL).toHaveBeenCalled()

    api.fetchPurchaseOrders.mockRejectedValueOnce(new Error('network'))
    await act(async () => buttonContaining('刷新')?.click())
    await flush()
    expect(ui.message.error).toHaveBeenCalledWith('采购订单汇总加载失败')
  })

  it('deletes a draft request from the record list', async () => {
    mount(
      <PurchaseRequestFormClient
        category="hardware"
        categoryLabel="五金材料"
        initialRequests={[request()]}
        initialTotal={1}
      />,
    )

    expect(container.textContent).toContain('删除')
    await act(async () => {
      Array.from(container.querySelectorAll<HTMLButtonElement>('button[data-confirm="true"]'))
        .find((button) => button.textContent === '删除')
        ?.click()
    })
    await flush()
    expect(actions.deletePurchaseRequest).toHaveBeenCalledWith(request().id)
    expect(ui.message.success).toHaveBeenCalledWith('采购申请已删除')
    expect(api.fetchPurchaseRequests).toHaveBeenCalled()
  })

  it('hides the delete action for non-draft requests', () => {
    mount(
      <PurchaseRequestFormClient
        category="hardware"
        categoryLabel="五金材料"
        initialRequests={[request({ status: 'pending_department_head' })]}
        initialTotal={1}
      />,
    )

    const deleteButtons = Array.from(container.querySelectorAll('button')).filter((button) =>
      button.textContent?.includes('删除')
    )
    expect(deleteButtons).toHaveLength(0)
  })

  it('maps delete failure to an error message', async () => {
    actions.deletePurchaseRequest.mockResolvedValueOnce({ code: 400, message: '仅草稿状态的采购申请可以删除', data: null })
    mount(
      <PurchaseRequestFormClient
        category="hardware"
        categoryLabel="五金材料"
        initialRequests={[request()]}
        initialTotal={1}
      />,
    )

    await act(async () => {
      Array.from(container.querySelectorAll<HTMLButtonElement>('button[data-confirm="true"]'))
        .find((button) => button.textContent === '删除')
        ?.click()
    })
    await flush()
    expect(ui.message.error).toHaveBeenCalledWith('仅草稿状态的采购申请可以删除')
  })
})
