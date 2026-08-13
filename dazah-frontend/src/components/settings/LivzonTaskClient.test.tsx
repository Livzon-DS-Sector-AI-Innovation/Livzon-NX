/* @vitest-environment happy-dom */
/* eslint-disable @typescript-eslint/no-explicit-any, react/display-name */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import dayjs from 'dayjs'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const actions = vi.hoisted(() => ({
  cancelLivzonTaskConfirmation: vi.fn(),
  executeLivzonTaskConfirmation: vi.fn(),
  requestLivzonTaskTool: vi.fn(),
}))

const api = vi.hoisted(() => ({
  fetchAgentInteractions: vi.fn(),
  fetchLivzonTaskRun: vi.fn(),
  fetchLivzonTaskRuns: vi.fn(),
  fetchLivzonTasks: vi.fn(),
  fetchLivzonTaskVersions: vi.fn(),
  submitAgentInteraction: vi.fn(),
}))

const ui = vi.hoisted(() => ({
  message: { error: vi.fn(), success: vi.fn() },
  modal: { confirm: vi.fn(), info: vi.fn() },
}))

vi.mock('@/actions/livzon-task', () => actions)
vi.mock('@/lib/api/agent', () => api)

vi.mock('antd', async () => {
  const React = await import('react')
  type AnyProps = Record<string, any>

  const createForm = () => ({
    values: { due_date: dayjs('2026-08-12') } as AnyProps,
    initialized: false,
    resetFields() { this.values = { due_date: dayjs('2026-08-12') } },
    setFieldsValue(values: AnyProps) { this.values = { ...this.values, ...values } },
    getFieldValue(name: string) { return this.values[name] },
    async validateFields() { return this.values },
  })

  const App = { useApp: () => ({ message: ui.message, modal: ui.modal }) }
  const Button = ({ children, onClick, disabled, loading, htmlType, ...props }: AnyProps) => (
    <button
      type={htmlType === 'submit' ? 'submit' : 'button'}
      disabled={disabled || loading}
      onClick={onClick}
      {...props}
    >{children}</button>
  )
  const Input = (props: AnyProps) => <input {...props} />
  Input.TextArea = (props: AnyProps) => <textarea {...props} />
  const InputNumber = (props: AnyProps) => <input type="number" {...props} />
  const DatePicker = ({ value, onChange, ...props }: AnyProps) => (
    <input {...props} value={value?.format?.('YYYY-MM-DD') ?? ''} onChange={(event) => onChange?.(dayjs(event.target.value))} />
  )
  const Checkbox = ({ children, onChange, ...props }: AnyProps) => (
    <label><input type="checkbox" {...props} onChange={onChange} />{children}</label>
  )
  const Select = ({ options = [], value, onChange, ...props }: AnyProps) => (
    <select {...props} value={value ?? ''} onChange={(event) => onChange?.(event.target.value)}>
      {options.map((option: AnyProps) => <option key={String(option.value)} value={option.value}>{option.label}</option>)}
    </select>
  )
  const Space = ({ children }: AnyProps) => <span>{children}</span>
  const Tag = ({ children }: AnyProps) => <span>{children}</span>
  const Text = ({ children }: AnyProps) => <span>{children}</span>
  const Paragraph = ({ children }: AnyProps) => <p>{children}</p>
  const Typography = { Text, Paragraph }
  const Descriptions = ({ children }: AnyProps) => <dl>{children}</dl>
  Descriptions.Item = ({ label, children }: AnyProps) => <div><dt>{label}</dt><dd>{children}</dd></div>

  const Form = ({ form, children, onFinish }: AnyProps) => {
    if (form && !form.initialized) form.initialized = true
    return <form onSubmit={(event) => { event.preventDefault(); void onFinish?.(form?.values) }}>{children}</form>
  }
  Form.useForm = () => {
    const [form] = React.useState(createForm)
    return [form]
  }
  Form.useWatch = (name: string, form: AnyProps) => form?.values?.[name]
  Form.Item = ({ children }: AnyProps) => <>{children}</>

  const renderTableCells = (columns: AnyProps[], rows: AnyProps[]) => rows.flatMap((row, rowIndex) => columns.map((column, columnIndex) => (
    <span key={`${rowIndex}-${columnIndex}`}>
      {column.title}
      {typeof column.render === 'function'
        ? column.render(column.dataIndex ? row[column.dataIndex] : undefined, row, rowIndex)
        : column.dataIndex ? row[column.dataIndex] : null}
    </span>
  )))
  const Table = ({ columns = [], dataSource = [] }: AnyProps) => (
    <div data-table="true">{renderTableCells(columns, dataSource)}</div>
  )

  const Tabs = ({ items = [], onChange }: AnyProps) => (
    <div>
      <nav>{items.map((item: AnyProps) => <button key={item.key} type="button" onClick={() => onChange?.(item.key)}>{item.label}</button>)}</nav>
      {items.map((item: AnyProps) => <section key={`content-${item.key}`}>{item.children}</section>)}
    </div>
  )
  const Timeline = ({ items = [] }: AnyProps) => <ol>{items.map((item: AnyProps, index: number) => <li key={index}>{item.children}</li>)}</ol>
  const Drawer = ({ open, title, children, extra, onClose }: AnyProps) => open ? (
    <aside role="dialog"><h2>{title}</h2>{extra}{children}<button type="button" onClick={onClose}>关闭</button></aside>
  ) : null
  const Modal = ({ open, title, children, onOk, onCancel, okText, cancelText }: AnyProps) => open ? (
    <div role="dialog"><h2>{title}</h2>{children}<button type="button" onClick={onOk}>{okText ?? '确定'}</button><button type="button" onClick={onCancel}>{cancelText ?? '取消'}</button></div>
  ) : null

  return {
    App,
    Button,
    Checkbox,
    DatePicker,
    Descriptions,
    Drawer,
    Form,
    Input,
    InputNumber,
    Modal,
    Select,
    Space,
    Table,
    Tabs,
    Tag,
    Timeline,
    Typography,
  }
})

import LivzonTaskClient from './LivzonTaskClient'

const automation = {
  id: 'automation-1',
  owner_user_id: 'user-1',
  name: '质量自动化',
  description: '自动处理质量事件',
  scope_type: 'tenant',
  status: 'enabled',
  active_version: 2,
  triggers: [{
    id: 'trigger-1', automation_id: 'automation-1', trigger_type: 'event', status: 'active',
    schedule: {}, timezone: 'Asia/Shanghai', next_fire_at: null,
  }],
  last_run_status: 'succeeded',
  last_run_at: '2026-08-12T08:00:00Z',
  updated_at: '2026-08-12T08:00:00Z',
}

const scheduled = {
  id: 'automation-2',
  owner_user_id: 'user-1',
  name: '库存定时任务',
  description: '定时检查库存',
  scope_type: 'tenant',
  status: 'draft',
  active_version: 1,
  triggers: [{
    id: 'trigger-2', automation_id: 'automation-2', trigger_type: 'schedule', status: 'active',
    schedule: { kind: 'interval', every: 15, unit: 'minutes' }, timezone: 'Asia/Shanghai', next_fire_at: '2026-08-12T09:15:00Z',
  }],
  last_run_status: 'failed',
  last_run_at: '2026-08-12T08:00:00Z',
  updated_at: '2026-08-12T08:00:00Z',
}

const version = {
  id: 'version-2', automation_id: 'automation-1', version: 2,
  definition: {
    name: '质量自动化', description: '自动处理质量事件',
    steps: [
      { key: 'check', name: '判断条件', type: 'condition', if_true: 'collect', if_false: 'end' },
      { key: 'collect', name: '收集数据', type: 'collect', mode: 'table_link', next: 'end' },
      { key: 'end', name: '结束', type: 'end' },
    ],
  },
  change_summary: '初始化', created_at: '2026-08-12T08:00:00Z',
}

const run = {
  id: 'run-1', automation_id: 'automation-1', status: 'failed', error_code: 'E_TOOL', error_message: '工具失败',
  started_at: '2026-08-12T08:00:00Z', created_at: '2026-08-12T08:00:00Z',
}

const interactions = [
  {
    type: 'form' as const, request_id: 'interaction-1', version: 1, title: '库存确认', summary: '请补充库存数据', status: 'pending',
    actions: [], expires_at: '2026-08-13T00:00:00Z', form_schema: [
      { key: 'name', label: '名称', type: 'text' as const, required: true },
      { key: 'quantity', label: '数量', type: 'number' as const },
      { key: 'date', label: '日期', type: 'date' as const },
      { key: 'category', label: '类别', type: 'single_select' as const, options: ['A', 'B'] },
      { key: 'tags', label: '标签', type: 'multi_select' as const, options: ['急', '常规'] },
      { key: 'confirmed', label: '确认', type: 'boolean' as const },
    ],
  },
  {
    type: 'table_link' as const, request_id: 'interaction-2', version: 2, title: '飞书表格填写', summary: '打开目标表', status: 'pending',
    actions: [], expires_at: '2026-08-13T00:00:00Z', form_schema: [], table_resource: { name: '库存表', url: 'https://feishu.example/table' },
  },
]

let container: HTMLDivElement
let root: Root

function mount() {
  container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
  act(() => root.render(<LivzonTaskClient />))
}

function findButton(text: string, onlyEnabled = false) {
  return Array.from(container.querySelectorAll('button')).find((button) =>
    button.textContent?.includes(text) && (!onlyEnabled || !button.disabled)
  )
}

function findExactButton(text: string) {
  return Array.from(container.querySelectorAll('button')).find((button) => button.textContent?.trim() === text)
}

async function flush() {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
    await Promise.resolve()
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  api.fetchLivzonTasks.mockResolvedValue({ items: [automation, scheduled], page: 1, page_size: 100, total: 2 })
  api.fetchAgentInteractions.mockResolvedValue({ items: interactions, page: 1, page_size: 100, total: 2 })
  api.fetchLivzonTaskVersions.mockResolvedValue([version])
  api.fetchLivzonTaskRuns.mockResolvedValue({ items: [run], page: 1, page_size: 10, total: 1 })
  api.fetchLivzonTaskRun.mockResolvedValue({ run, steps: [{ id: 'step-run-1', step_key: 'check', operation: 'quality.list', attempt: 1, status: 'failed', error_code: 'E_TOOL', error_message: '工具失败', started_at: run.started_at }] })
  api.submitAgentInteraction.mockResolvedValue({ ...interactions[0], status: 'completed' })
  actions.executeLivzonTaskConfirmation.mockResolvedValue({ ok: true })
  actions.cancelLivzonTaskConfirmation.mockResolvedValue(undefined)
  actions.requestLivzonTaskTool.mockImplementation(async ({ operation }: { operation: string }) => (
    operation === 'agent.simulate_automation'
      ? { ok: true, data: { dry_run_plan: [{ step_key: 'check', type: 'tool', operation: 'quality.list', suppressed: true }] } }
      : {
        ok: false,
        requires_confirmation: true,
        confirmation: { id: 'confirmation-1', summary: '确认 Livzon Task 操作', risk_level: 'medium' },
      }
  ))
})

afterEach(() => {
  act(() => root?.unmount())
  container?.remove()
})

describe('LivzonTaskClient', () => {
  it('loads tasks and exercises details, schedules, dry-run, toggle, edit, and interaction forms', async () => {
    mount()
    await flush()
    expect(container.textContent).toContain('Livzon Task')
    expect(container.textContent).toContain('填写请求 2')
    expect(container.textContent).toContain('每 15 分钟执行')

    await act(async () => findButton('试运行')?.click())
    await flush()
    expect(ui.modal.info).toHaveBeenCalledWith(expect.objectContaining({ title: '质量自动化 · 试运行预览' }))

    await act(async () => findButton('详情')?.click())
    await flush()
    expect(api.fetchLivzonTaskRun).toHaveBeenCalledWith('run-1')
    expect(container.querySelector('[role="dialog"]')?.textContent).toContain('执行步骤与分支')
    expect(container.querySelector('[role="dialog"]')?.textContent).toContain('工具失败')
    act(() => findButton('关闭')?.click())

    await act(async () => findButton('修改', true)?.click())
    await flush()
    expect(container.querySelector('[role="dialog"]')?.textContent).toContain('修改自动化流程')
    await act(async () => findButton('提交修改')?.click())
    await flush()
    await ui.modal.confirm.mock.calls.at(-1)?.[0].onOk()
    await flush()
    expect(actions.requestLivzonTaskTool).toHaveBeenCalledWith(expect.objectContaining({ operation: 'agent.update_automation' }))
    expect(actions.executeLivzonTaskConfirmation).toHaveBeenCalledWith('confirmation-1')

    await act(async () => findButton('禁用')?.click())
    await flush()
    await ui.modal.confirm.mock.calls.at(-1)?.[0].onOk()
    await flush()
    expect(actions.requestLivzonTaskTool).toHaveBeenCalledWith(expect.objectContaining({ operation: 'agent.set_automation_enabled' }))

    act(() => findButton('定时任务')?.click())
    await flush()
    expect(container.textContent).toContain('定时任务')

    await act(async () => findExactButton('填写')?.click())
    await flush()
    expect(container.querySelector('[role="dialog"]')?.textContent).toContain('库存确认')
    await act(async () => findButton('提交并写入飞书表格')?.click())
    await flush()
    expect(api.submitAgentInteraction).toHaveBeenCalledWith(interactions[0], expect.any(Object))
    expect(ui.message.success).toHaveBeenCalledWith('填写成功，已写入目标表')

    await act(async () => findExactButton('打开并完成')?.click())
    await flush()
    await act(async () => findButton('已完成，校验并继续')?.click())
    await flush()
    expect(ui.message.success).toHaveBeenCalledWith('已完成校验，流程将继续')
  })

  it('reports interaction, dry-run, detail, and loading failures', async () => {
    mount()
    await flush()

    actions.requestLivzonTaskTool.mockRejectedValueOnce(new Error('试运行失败'))
    await act(async () => findButton('试运行')?.click())
    await flush()
    expect(ui.message.error).toHaveBeenCalledWith('试运行失败')

    api.fetchLivzonTaskVersions.mockRejectedValueOnce(new Error('详情失败'))
    await act(async () => findButton('详情')?.click())
    await flush()
    expect(ui.message.error).toHaveBeenCalledWith('详情失败')
    act(() => findButton('关闭')?.click())

    api.fetchAgentInteractions.mockRejectedValueOnce(new Error('加载失败'))
    await act(async () => findButton('刷新')?.click())
    await flush()
    expect(ui.message.error).toHaveBeenCalledWith('加载失败')

    await act(async () => findExactButton('填写')?.click())
    await flush()
    expect(container.querySelector('[role="dialog"]')?.textContent).toContain('库存确认')
    api.submitAgentInteraction.mockRejectedValueOnce(new Error('提交失败'))
    await act(async () => findButton('提交并写入飞书表格')?.click())
    await flush()
    expect(ui.message.error).toHaveBeenLastCalledWith('提交失败')
  })
})
