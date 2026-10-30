/* @vitest-environment happy-dom */

import { act, createElement, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  form: {
    setFieldsValue: vi.fn(),
    validateFields: vi.fn(async () => ({})),
    resetFields: vi.fn(),
  },
  permissions: { canOperate: true },
  renderFeishuValue: vi.fn(),
  getSafetyPageTableRecords: vi.fn(),
  getSafetyPageTableStats: vi.fn(),
  getSafetyPageTableFieldValues: vi.fn(),
  createSafetyPageTableRecord: vi.fn(),
  updateSafetyPageTableRecord: vi.fn(),
  uploadSafetyPageTableAttachment: vi.fn(),
  statsSelect: vi.fn(),
  capturedTableColumns: [] as Array<Record<string, unknown>>,
}))

vi.mock('@/actions/safety', () => ({
  getSafetyPageTableRecords: mocks.getSafetyPageTableRecords,
  getSafetyPageTableStats: mocks.getSafetyPageTableStats,
  getSafetyPageTableFieldValues: mocks.getSafetyPageTableFieldValues,
  createSafetyPageTableRecord: mocks.createSafetyPageTableRecord,
  updateSafetyPageTableRecord: mocks.updateSafetyPageTableRecord,
  uploadSafetyPageTableAttachment: mocks.uploadSafetyPageTableAttachment,
}))

vi.mock('@/hooks/usePagePermissions', () => ({
  usePagePermissions: () => ({
    canAccess: true,
    canQuery: true,
    canOperate: mocks.permissions.canOperate,
    canDelete: true,
    canExport: true,
    canImport: true,
    canSync: true,
    canApprove: true,
    canReject: true,
  }),
}))

vi.mock('@/components/quality/inspection/renderFeishuValue', () => ({
  renderFeishuValue: mocks.renderFeishuValue,
}))

vi.mock('@/components/safety/PageFeishuStatsBar', async () => {
  const { createElement } = await import('react')
  return {
    default: ({ onSelect }: { onSelect?: (field: string, key: string) => void }) => {
      return createElement(
      'button',
      {
        type: 'button',
        'data-stats-select': '整改情况',
        onClick: () => onSelect?.('整改情况', '已整改'),
      },
        'stats-select'
      )
    },
  }
})

vi.mock('@/components/shared/PlatformNotice', async () => {
  const { createElement } = await import('react')
  return {
    default: ({ title, description }: { title?: ReactNode; description?: ReactNode }) =>
      createElement(
        'div',
        { 'data-notice': 'true' },
        title as ReactNode,
        createElement('span', { 'data-description': 'true' }, description as ReactNode)
      ),
  }
})

vi.mock('@ant-design/icons', () => {
  const Icon = () => null
  return {
    ArrowUpOutlined: Icon,
    CloudUploadOutlined: Icon,
    PlusOutlined: Icon,
    ReloadOutlined: Icon,
    SaveOutlined: Icon,
    SearchOutlined: Icon,
  }
})

type Column = {
  key?: string
  render?: (value: unknown, row: Record<string, unknown>) => ReactNode
}
type Row = { record_id: string; fields: Record<string, unknown> }
type AnyProps = Record<string, unknown> & { children?: ReactNode }
type ChangeHandler = ((event: { target: { value: string } }) => void) | undefined

vi.mock('antd', async () => {
  const { createElement } = await import('react')
  const dayjs = (await import('dayjs')).default

  const Box = ({ children, title, extra }: AnyProps) =>
    createElement('div', null, title as ReactNode, extra as ReactNode, children as ReactNode)
  const Text = ({ children }: AnyProps) => createElement('span', null, children as ReactNode)
  const Button = ({ children, onClick, disabled }: AnyProps) =>
    createElement(
      'button',
      { type: 'button', disabled: Boolean(disabled), onClick: onClick as never },
      children as ReactNode
    )
  const Input = Object.assign(
    ({ value, onChange, placeholder }: AnyProps) =>
      createElement('input', {
        value: (value as string) ?? '',
        placeholder: placeholder as string,
        ref: (node: HTMLInputElement | null) => {
          if (!node) return
          node.onchange = () =>
            (onChange as ChangeHandler)?.({ target: { value: node.value } })
        },
      }),
    { TextArea: Box }
  )
  const Table = ({
    columns,
    dataSource,
    onChange,
    onRow,
    rowClassName,
  }: {
    columns?: Column[]
    dataSource?: Row[]
    onChange?: (pagination: { current?: number; pageSize?: number }) => void
    onRow?: (row: Row) => { onClick?: () => void }
    rowClassName?: (row: Row) => string
  }) => {
    mocks.capturedTableColumns = columns ?? []
    return createElement(
      'div',
      null,
      createElement(
        'button',
        {
          type: 'button',
          'data-table-page': '2',
          onClick: () => onChange?.({ current: 2, pageSize: 20 }),
        },
        'goto-page-2'
      ),
      createElement(
        'table',
        null,
        createElement(
          'tbody',
          null,
          (dataSource ?? []).map((row) => {
            const rowProps = onRow?.(row)
            return createElement(
              'tr',
              {
                key: row.record_id,
                'data-row': row.record_id,
                className: rowClassName?.(row) ?? '',
                onClick: () => rowProps && rowProps.onClick && rowProps.onClick(),
              },
              (columns ?? []).map((column, index) =>
                createElement(
                  'td',
                  { key: column.key ?? index },
                  column.render?.(undefined, row) as ReactNode
                )
              )
            )
          })
        )
      )
    )
  }
  const Upload = ({ children, beforeUpload, disabled }: AnyProps) =>
    createElement(
      'div',
      null,
      createElement(
        'button',
        {
          type: 'button',
          'data-upload': 'true',
          disabled: Boolean(disabled),
          onClick: () =>
            (beforeUpload as ((file: File) => boolean) | undefined)?.(
              new File(['abc'], 'photo.png', { type: 'image/png' })
            ),
        },
        'upload'
      ),
      children as ReactNode
    )

  return {
    App: { useApp: () => ({ message: mocks.message }) },
    Avatar: ({ children, src }: AnyProps) =>
      createElement('span', { 'data-avatar-src': (src as string) ?? '' }, children as ReactNode),
    Button,
    Card: Box,
    Segmented: Box,
    DatePicker: Object.assign(
      ({ value, onChange, placeholder }: AnyProps) =>
        createElement('input', {
          'data-date-picker': String(placeholder ?? ''),
          value: value ? dayjs(value as string).format('YYYY-MM-DD') : '',
          ref: (node: HTMLInputElement | null) => {
            if (!node) return
            node.onchange = () =>
              (onChange as unknown as (value: unknown) => void)?.(
                node.value ? dayjs(node.value) : null
              )
          },
        }),
      {
        RangePicker: ({ value, onChange }: AnyProps) => {
          const range = (value as Array<unknown> | null) ?? []
          return createElement('input', {
            'data-range-picker': 'true',
            value: range
              .map((item) => (item ? dayjs(item as string).format('YYYY-MM-DD') : ''))
              .join('~'),
            ref: (node: HTMLInputElement | null) => {
              if (!node) return
              node.onchange = () => {
                const parts = node.value.split('~')
                ;(onChange as unknown as (value: unknown) => void)?.([
                  parts[0] ? dayjs(parts[0]) : null,
                  parts[1] ? dayjs(parts[1]) : null,
                ])
              }
            },
          })
        },
      }
    ),
    Drawer: Box,
    Form: Object.assign(({ children }: AnyProps) => createElement('form', null, children as ReactNode), {
      Item: Box,
      useForm: () => [mocks.form],
    }),
    Input,
    InputNumber: Box,
    Select: ({ value, onChange, placeholder }: AnyProps) =>
      createElement('input', {
        'data-select': String(placeholder ?? ''),
        value: (value as string) ?? '',
        ref: (node: HTMLInputElement | null) => {
          if (!node) return
          node.onchange = () =>
            (onChange as unknown as (value: unknown) => void)?.(
              node.value || undefined
            )
        },
      }),
    Space: Box,
    Switch: Box,
    Table,
    Tag: Text,
    Typography: { Text, Paragraph: Text },
    Upload,
  }
})

import PageFeishuTable from './PageFeishuTable'

const PAGE_KEY = 'safety:risk-hazard:hazard-inspection:hazard-duty'

mocks.renderFeishuValue.mockImplementation(
  (value: unknown) => `feishu-rendered:${JSON.stringify(value)}`
)

const columns = [
  {
    field_id: 'fld1',
    name: '记录编号',
    type: 1,
    kind: 'text',
    is_primary: true,
    options: [],
    editable: true,
  },
  {
    field_id: 'fld2',
    name: '照片',
    type: 17,
    kind: 'attachment',
    is_primary: false,
    options: [],
    editable: true,
  },
  {
    field_id: 'fld3',
    name: '值班人员',
    type: 11,
    kind: 'person',
    is_primary: false,
    options: [],
    editable: true,
  },
  {
    field_id: 'fld4',
    name: '整改情况',
    type: 3,
    kind: 'select',
    is_primary: false,
    options: ['未整改', '已整改'],
    editable: true,
  },
  {
    field_id: 'fld5',
    name: '公式列',
    type: 20,
    kind: 'readonly',
    is_primary: false,
    options: [],
    editable: false,
  },
]

const rows = [
  {
    record_id: 'rec-1',
    fields: {
      记录编号: 'YH-20261011-03',
      照片: [{ file_token: 'tok-1', name: 'a.jpg', type: 'image/jpeg' }],
      值班人员: [{ id: 'ou_1', name: '徐亮', avatar_url: 'https://s1/a.png' }],
      整改情况: '未整改',
      公式列: '只读内容',
    },
  },
  { record_id: 'rec-2', fields: {} },
]

function initialData() {
  return {
    columns,
    records: rows,
    total: 2,
    page: 1,
    page_size: 20,
    truncated: false,
  }
}

function okRecords() {
  return { code: 200, data: initialData() }
}

let rendered: { root: Root; container: HTMLDivElement } | undefined

function renderTable(props: Partial<Parameters<typeof PageFeishuTable>[0]> = {}) {
  const container = document.createElement('div')
  document.body.append(container)
  const root = createRoot(container)
  act(() => {
    root.render(
      createElement(PageFeishuTable, {
        pageKey: PAGE_KEY,
        pageName: '24小时值班隐患',
        initialData: initialData(),
        initialStats: null,
        initialError: null,
        ...props,
      })
    )
  })
  return { root, container }
}

async function settle() {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
}

function findButton(container: HTMLElement, text: string): HTMLButtonElement | undefined {
  return Array.from(container.querySelectorAll('button')).find((button) =>
    button.textContent?.includes(text)
  ) as HTMLButtonElement | undefined
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.permissions.canOperate = true
  mocks.getSafetyPageTableRecords.mockResolvedValue(okRecords())
  mocks.getSafetyPageTableStats.mockResolvedValue({
    code: 200,
    data: { page_key: PAGE_KEY, page_name: '24小时值班隐患', total: 2, groups: [] },
  })
  mocks.getSafetyPageTableFieldValues.mockResolvedValue({
    code: 200,
    data: {
      page_key: PAGE_KEY,
      field: 'x',
      table_id: 'tblMain',
      values: [{ value: '201一车间', count: 26 }],
    },
  })
  mocks.updateSafetyPageTableRecord.mockResolvedValue({
    code: 200,
    data: rows[0],
  })
  mocks.uploadSafetyPageTableAttachment.mockResolvedValue({
    code: 200,
    data: { attachments: [{ file_token: 'tok-new', name: 'photo.png' }] },
  })
  mocks.createSafetyPageTableRecord.mockResolvedValue({
    code: 200,
    data: { record_id: 'rec-new', fields: {} },
  })
})

afterEach(() => {
  if (rendered) {
    act(() => rendered?.root.unmount())
    rendered.container.remove()
    rendered = undefined
  }
})

describe('PageFeishuTable（静态渲染）', () => {
  it('delegates attachment and person cells to the shared feishu renderer', async () => {
    rendered = renderTable()
    await settle()

    expect(qualityOrLocalMarkup()).toContain('feishu-rendered:')
    expect(qualityOrLocalMarkup()).toContain('tok-1')
    expect(qualityOrLocalMarkup()).toContain('YH-20261011-03')
    expect(qualityOrLocalMarkup()).toContain('未整改')
    expect(qualityOrLocalMarkup()).toContain('只读内容')
    expect(qualityOrLocalMarkup()).toContain('共 2 条')
  })

  it('builds attachment urls ending with /content so thumbnails can be derived', async () => {
    rendered = renderTable()
    await settle()

    // 附件渲染调用才带 attachmentUrlBuilder（人员渲染没有第 5 个参数）
    const call = mocks.renderFeishuValue.mock.calls.find((item) => item.length >= 5)
    const options = call?.[4] as
      | { attachmentUrlBuilder: (e: string, r: string, t: string) => string }
      | undefined
    expect(options).toBeDefined()
    const url = options!.attachmentUrlBuilder('', 'rec-9', 'tok-9')
    expect(url).toBe(
      `/api/v1/safety/page-tables/${encodeURIComponent(PAGE_KEY)}/records/rec-9/attachments/${encodeURIComponent('照片')}/tok-9/content`,
    )
  })

  it('surfaces a configuration error notice with the settings hint', async () => {
    // 交互模式下挂载后会兜底拉取；让拉取失败以维持错误态
    mocks.getSafetyPageTableRecords.mockResolvedValue({
      code: 500,
      message: '「24小时值班隐患」尚未配置多维表格或已停用',
    })
    rendered = renderTable({ initialData: null })
    await settle()

    expect(rendered.container.innerHTML).toContain('无法读取多维表格数据')
    expect(rendered.container.innerHTML).toContain('尚未配置多维表格')
    expect(rendered.container.innerHTML).toContain('页面数据表映射')
  })

  it('warns when the record set is truncated', async () => {
    rendered = renderTable({
      initialData: {
        columns,
        records: [],
        total: 5000,
        page: 1,
        page_size: 20,
        truncated: true,
      },
    })
    await settle()

    expect(rendered.container.innerHTML).toContain('仅加载最近 2000 条')
  })
})

function qualityOrLocalMarkup(): string {
  return rendered!.container.innerHTML
}

describe('PageFeishuTable（交互）', () => {
  it('loads data on mount when server-side data is missing', async () => {
    rendered = renderTable({ initialData: null })
    await settle()

    expect(mocks.getSafetyPageTableRecords).toHaveBeenCalledWith(
      expect.objectContaining({ pageKey: PAGE_KEY, page: 1, pageSize: 20 })
    )
    expect(mocks.getSafetyPageTableStats).toHaveBeenCalledWith({ pageKey: PAGE_KEY })
  })

  it('skips the stats dashboard entirely when showStats is false', async () => {
    rendered = renderTable({ initialData: null, showStats: false })
    await settle()

    expect(mocks.getSafetyPageTableRecords).toHaveBeenCalled()
    expect(mocks.getSafetyPageTableStats).not.toHaveBeenCalled()
    expect(
      rendered.container.querySelector('[data-stats-select]')
    ).toBeNull()
  })

  it('keeps only summary columns in the table and moves the rest to detail', async () => {
    const manyColumns = [
      ...Array.from({ length: 10 }, (_, index) => ({
        field_id: `fld-biz${index}`,
        name: `业务列${index + 1}`,
        type: 1,
        kind: 'text',
        is_primary: false,
        options: [],
        editable: true,
      })),
      {
        field_id: 'fld-long',
        name: '准备措施',
        type: 1,
        kind: 'text',
        is_primary: false,
        options: [],
        editable: true,
      },
      {
        field_id: 'fld-chk',
        name: '投料前抽风机是否开启',
        type: 7,
        kind: 'checkbox',
        is_primary: false,
        options: [],
        editable: true,
      },
    ]
    const manyRows = [
      {
        record_id: 'rec-1',
        fields: {
          业务列1: 'A',
          准备措施: '超'.repeat(120),
          投料前抽风机是否开启: true,
        },
      },
    ]
    rendered = renderTable({
      summarizeColumns: true,
      initialData: {
        columns: manyColumns,
        records: manyRows,
        total: 1,
        page: 1,
        page_size: 20,
        truncated: false,
      },
    })
    await settle()

    const html = rendered.container.innerHTML
    // 12 列里表格只渲染 10 个摘要单元格（10 个短文本列）
    expect(
      rendered.container.querySelectorAll('tbody tr[data-row="rec-1"] td')
        .length
    ).toBe(10)
    // 勾选清单与长文本列只在详情中查看，不出现在表格里
    expect(html).not.toContain('准备措施')
    expect(html).not.toContain('投料前抽风机是否开启')
    expect(html).toContain('其余 2 个字段')
  })

  it('wraps long-option select columns instead of tag truncation', async () => {
    const longOption = '防毒面罩、防静电工作服、酸碱防护服、耐酸碱鞋、耐酸碱手套'
    const protectColumns = [
      {
        field_id: 'fld-1',
        name: '申请编号',
        type: 1,
        kind: 'text',
        is_primary: true,
        options: [],
        editable: true,
      },
      {
        field_id: 'fld-2',
        name: '个人防护',
        type: 3,
        kind: 'select',
        is_primary: false,
        options: [longOption, '防毒面罩'],
        editable: true,
      },
    ]
    rendered = renderTable({
      summarizeColumns: true,
      initialData: {
        columns: protectColumns,
        records: [
          { record_id: 'rec-1', fields: { 申请编号: 'A', 个人防护: longOption } },
        ],
        total: 1,
        page: 1,
        page_size: 20,
        truncated: false,
      },
    })
    await settle()

    const html = rendered.container.innerHTML
    // 选项为长句的单选列按长文本渲染：完整内容 + 自动换行样式
    expect(html).toContain(longOption)
    expect(html).toContain('pre-wrap')
  })

  it('always keeps status columns in the summary beyond the cap', async () => {
    const manyColumns = [
      ...Array.from({ length: 12 }, (_, index) => ({
        field_id: `fld-biz${index}`,
        name: `业务列${index + 1}`,
        type: 1,
        kind: 'text',
        is_primary: false,
        options: [],
        editable: true,
      })),
      {
        field_id: 'fld-status',
        name: '申请状态',
        type: 3,
        kind: 'select',
        is_primary: false,
        options: ['已通过', '审批中'],
        editable: true,
      },
    ]
    rendered = renderTable({
      summarizeColumns: true,
      initialData: {
        columns: manyColumns,
        records: [
          { record_id: 'rec-1', fields: { 业务列1: 'A', 申请状态: '已通过' } },
        ],
        total: 1,
        page: 1,
        page_size: 20,
        truncated: false,
      },
    })
    await settle()

    const tds = rendered.container.querySelectorAll(
      'tbody tr[data-row="rec-1"] td'
    )
    // 摘要仍为 10 列，且最后一列是状态列
    expect(tds.length).toBe(10)
    expect(tds[tds.length - 1]?.textContent).toContain('已通过')
    expect(rendered.container.innerHTML).toContain('其余 3 个字段')
  })

  it('shows summary-demoted fields in the detail drawer', async () => {
    const manyColumns = [
      {
        field_id: 'fld-biz1',
        name: '业务列1',
        type: 1,
        kind: 'text',
        is_primary: false,
        options: [],
        editable: true,
      },
      {
        field_id: 'fld-long',
        name: '准备措施',
        type: 1,
        kind: 'text',
        is_primary: false,
        options: [],
        editable: true,
      },
      {
        field_id: 'fld-chk',
        name: '投料前抽风机是否开启',
        type: 7,
        kind: 'checkbox',
        is_primary: false,
        options: [],
        editable: true,
      },
    ]
    const manyRows = [
      {
        record_id: 'rec-1',
        fields: {
          业务列1: 'A',
          准备措施: '超'.repeat(120),
          投料前抽风机是否开启: true,
        },
      },
    ]
    rendered = renderTable({
      summarizeColumns: true,
      initialData: {
        columns: manyColumns,
        records: manyRows,
        total: 1,
        page: 1,
        page_size: 20,
        truncated: false,
      },
    })
    await settle()

    act(() =>
      rendered!.container
        .querySelector('tr[data-row="rec-1"]')
        ?.dispatchEvent(new Event('click', { bubbles: true }))
    )
    await settle()

    // 详情抽屉覆盖全部字段：被收起的长文本与勾选列都进入了表单初始值
    expect(mocks.form.setFieldsValue).toHaveBeenCalledWith(
      expect.objectContaining({
        业务列1: 'A',
        准备措施: '超'.repeat(120),
        投料前抽风机是否开启: true,
      })
    )
  })

  it('renders every column when summarizeColumns is not enabled', async () => {
    const manyColumns = [
      ...Array.from({ length: 12 }, (_, index) => ({
        field_id: `fld-biz${index}`,
        name: `业务列${index + 1}`,
        type: 1,
        kind: 'text',
        is_primary: false,
        options: [],
        editable: true,
      })),
    ]
    const manyRows = [
      {
        record_id: 'rec-1',
        fields: { 业务列1: 'A', 业务列12: '超'.repeat(120) },
      },
    ]
    rendered = renderTable({
      initialData: {
        columns: manyColumns,
        records: manyRows,
        total: 1,
        page: 1,
        page_size: 20,
        truncated: false,
      },
    })
    await settle()

    // 未启用主要列模式（如 24小时值班隐患页）：全列展示、无收起提示
    expect(
      rendered.container.querySelectorAll('tbody tr[data-row="rec-1"] td')
        .length
    ).toBe(12)
    expect(rendered.container.innerHTML).not.toContain('其余')
  })

  it('wraps long text columns at a fixed width in full-column mode', async () => {
    const ledgerColumns = [
      {
        field_id: 'fld-dept',
        name: '部门/车间',
        type: 1,
        kind: 'text',
        is_primary: false,
        options: [],
        editable: true,
      },
      {
        field_id: 'fld-content',
        name: '隐患内容',
        type: 1,
        kind: 'text',
        is_primary: false,
        options: [],
        editable: true,
      },
    ]
    const longContent = '反应釜密封老化导致物料泄漏，需立即更换密封件并排查同类设备'.repeat(3)
    rendered = renderTable({
      initialData: {
        columns: ledgerColumns,
        records: [
          {
            record_id: 'rec-1',
            fields: { '部门/车间': '201一车间', 隐患内容: longContent },
          },
        ],
        total: 1,
        page: 1,
        page_size: 20,
        truncated: false,
      },
    })
    await settle()

    const html = rendered.container.innerHTML
    // 文本列一律定宽换行（约 150px）：两列都是 text → 两个换行 div
    expect(html).toContain(longContent)
    expect((html.match(/pre-wrap/g) ?? []).length).toBe(2)
    expect(html).toContain('break-word')
    // 超长内容按 4 行截断保持行高紧凑（完整内容在详情抽屉查看）；
    // happy-dom 会丢弃 -webkit- 前缀属性，这里断言截断用的 overflow
    expect((html.match(/overflow: hidden/g) ?? []).length).toBe(2)
    expect(html).toContain('201一车间')
  })

  it('combines date and select conditions in summary mode', async () => {
    const filterColumns = [
      {
        field_id: 'fld-1',
        name: '申请编号',
        type: 1,
        kind: 'text',
        is_primary: true,
        options: [],
        editable: true,
      },
      {
        field_id: 'fld-2',
        name: '作业日期',
        type: 5,
        kind: 'date',
        is_primary: false,
        options: [],
        editable: true,
      },
      {
        field_id: 'fld-3',
        name: '申请状态',
        type: 3,
        kind: 'select',
        is_primary: false,
        options: ['已通过', '审批中'],
        editable: true,
      },
    ]
    const filterRows = [{ record_id: 'rec-1', fields: { 申请编号: 'A' } }]
    rendered = renderTable({
      summarizeColumns: true,
      initialDateFilter: { field: '作业日期', value: '2026-10-13' },
      initialData: {
        columns: filterColumns,
        records: filterRows,
        total: 1,
        page: 1,
        page_size: 20,
        truncated: false,
      },
    })
    await settle()

    // 筛选条渲染：日期控件 + 带选项的下拉
    const datePicker = rendered.container.querySelector(
      '[data-date-picker]'
    ) as HTMLInputElement
    const statusSelect = rendered.container.querySelector(
      '[data-select="申请状态"]'
    ) as HTMLInputElement
    expect(datePicker).toBeTruthy()
    expect(datePicker.value).toBe('2026-10-13')
    expect(statusSelect).toBeTruthy()

    // 选择下拉后按 当天日期 + 选项 组合条件请求
    act(() => {
      statusSelect.value = '已通过'
      statusSelect.dispatchEvent(new Event('change'))
    })
    await settle()

    const call = mocks.getSafetyPageTableRecords.mock.calls.at(-1)?.[0] as {
      conditions?: Array<{ field: string; value: string }>
    }
    expect(call.conditions).toEqual([
      { field: '作业日期', value: '2026-10-13' },
      { field: '申请状态', value: '已通过' },
    ])

    // 清空日期后不再带日期条件（查看全部）
    act(() => {
      datePicker.value = ''
      datePicker.dispatchEvent(new Event('change'))
    })
    await settle()

    const cleared = mocks.getSafetyPageTableRecords.mock.calls.at(-1)?.[0] as {
      conditions?: Array<{ field: string; value: string }>
    }
    expect(cleared.conditions).toEqual([{ field: '申请状态', value: '已通过' }])
  })

  it('reloads with the keyword when 查询 is clicked', async () => {
    rendered = renderTable()
    await settle()
    mocks.getSafetyPageTableRecords.mockClear()

    const input = rendered.container.querySelector('input') as HTMLInputElement
    input.value = 'YH-'
    input.dispatchEvent(new Event('change', { bubbles: true }))
    await settle()
    act(() => findButton(rendered!.container, '查询')?.click())
    await settle()

    expect(mocks.getSafetyPageTableRecords).toHaveBeenCalledWith(
      expect.objectContaining({ keyword: 'YH-', page: 1 })
    )
  })

  it('reloads via the 刷新 button', async () => {
    rendered = renderTable()
    await settle()
    mocks.getSafetyPageTableRecords.mockClear()

    act(() => findButton(rendered!.container, '刷新')?.click())
    await settle()

    expect(mocks.getSafetyPageTableRecords).toHaveBeenCalledTimes(1)
  })

  it('requests page 2 through the table pagination change', async () => {
    rendered = renderTable()
    await settle()
    mocks.getSafetyPageTableRecords.mockClear()

    act(() =>
      rendered!.container.querySelector('button[data-table-page="2"]')?.dispatchEvent(
        new Event('click', { bubbles: true })
      )
    )
    await settle()

    expect(mocks.getSafetyPageTableRecords).toHaveBeenCalledWith(
      expect.objectContaining({ page: 2, pageSize: 20 })
    )
  })

  it('opens the detail drawer when a row is clicked', async () => {
    rendered = renderTable()
    await settle()

    act(() =>
      rendered!.container
        .querySelector('tr[data-row="rec-1"]')
        ?.dispatchEvent(new Event('click', { bubbles: true }))
    )
    await settle()

    expect(mocks.form.setFieldsValue).toHaveBeenCalledWith(
      expect.objectContaining({ 记录编号: 'YH-20261011-03', 整改情况: '未整改' })
    )
    // 人员字段取 open_id 列表，附件字段不入表单
    const payload = mocks.form.setFieldsValue.mock.calls.at(-1)?.[0] as Record<
      string,
      unknown
    >
    expect(payload['值班人员']).toEqual(['ou_1'])
    expect('照片' in payload).toBe(false)
  })

  it('saves edits back to feishu and refreshes the row', async () => {
    rendered = renderTable()
    await settle()
    act(() =>
      rendered!.container
        .querySelector('tr[data-row="rec-1"]')
        ?.dispatchEvent(new Event('click', { bubbles: true }))
    )
    await settle()

    act(() => findButton(rendered!.container, '保存')?.click())
    await settle()

    expect(mocks.updateSafetyPageTableRecord).toHaveBeenCalledWith(
      expect.objectContaining({ pageKey: PAGE_KEY, recordId: 'rec-1' })
    )
    expect(mocks.message.success).toHaveBeenCalledWith('已保存到飞书多维表格')
  })

  it('surfaces save failures', async () => {
    mocks.updateSafetyPageTableRecord.mockResolvedValue({
      code: 500,
      message: '字段校验失败',
    })
    rendered = renderTable()
    await settle()
    act(() =>
      rendered!.container
        .querySelector('tr[data-row="rec-1"]')
        ?.dispatchEvent(new Event('click', { bubbles: true }))
    )
    await settle()

    act(() => findButton(rendered!.container, '保存')?.click())
    await settle()

    expect(mocks.message.error).toHaveBeenCalledWith('字段校验失败')
  })

  it('disables saving without operate permission', async () => {
    mocks.permissions.canOperate = false
    rendered = renderTable()
    await settle()
    act(() =>
      rendered!.container
        .querySelector('tr[data-row="rec-1"]')
        ?.dispatchEvent(new Event('click', { bubbles: true }))
    )
    await settle()

    const save = findButton(rendered!.container, '保存')
    expect(save?.disabled).toBe(true)
    expect(rendered!.container.innerHTML).toContain('当前账号只有查看权限')
  })

  it('filters through the stats bar and toggles the filter off', async () => {
    rendered = renderTable()
    await settle()
    mocks.getSafetyPageTableRecords.mockClear()

    act(() =>
      rendered!.container
        .querySelector('button[data-stats-select="整改情况"]')
        ?.dispatchEvent(new Event('click', { bubbles: true }))
    )
    await settle()
    expect(mocks.getSafetyPageTableRecords).toHaveBeenCalledWith(
      expect.objectContaining({ filterField: '整改情况', filterValue: '已整改' })
    )

    // 再点一次同一分类取消筛选
    act(() =>
      rendered!.container
        .querySelector('button[data-stats-select="整改情况"]')
        ?.dispatchEvent(new Event('click', { bubbles: true }))
    )
    await settle()
    expect(mocks.getSafetyPageTableRecords).toHaveBeenCalledWith(
      expect.objectContaining({ filterField: undefined, filterValue: undefined })
    )
  })

  it('uploads attachments from the detail drawer', async () => {
    rendered = renderTable()
    await settle()
    act(() =>
      rendered!.container
        .querySelector('tr[data-row="rec-1"]')
        ?.dispatchEvent(new Event('click', { bubbles: true }))
    )
    await settle()

    const upload = rendered.container.querySelector(
      'button[data-upload="true"]'
    ) as HTMLButtonElement
    act(() => upload?.click())
    await settle()

    expect(mocks.uploadSafetyPageTableAttachment).toHaveBeenCalledWith(
      expect.objectContaining({
        pageKey: PAGE_KEY,
        recordId: 'rec-1',
        fieldName: '照片',
      })
    )
    expect(mocks.message.success).toHaveBeenCalledWith('附件已上传到飞书多维表格')
  })

  it('reports load failures through the notice bar', async () => {
    mocks.getSafetyPageTableRecords.mockResolvedValue({
      code: 500,
      message: '飞书不可用',
    })
    rendered = renderTable({ initialData: null })
    await settle()

    expect(rendered.container.innerHTML).toContain('无法读取多维表格数据')
    expect(rendered.container.innerHTML).toContain('飞书不可用')
  })
})
describe('PageFeishuTable（默认排序与子表下拉）', () => {
  it('applies the default sort field to the mount fallback load', async () => {
    rendered = renderTable({ initialData: null, defaultSortField: '部门/车间' })
    await settle()

    expect(mocks.getSafetyPageTableRecords).toHaveBeenCalledWith(
      expect.objectContaining({ sortField: '部门/车间', sortDirection: 'asc' })
    )
  })

  it('renders a table selector instead of tabs and reloads on change', async () => {
    const tabs = [
      { table_id: 'tblMain', tab_name: '隐患台账', is_primary: true, record_count: 1480 },
      { table_id: 'tblSub', tab_name: '2024年公司级检查', is_primary: false, record_count: 442 },
    ]
    rendered = renderTable({ tabs, defaultSortField: '部门/车间' })
    await settle()
    mocks.getSafetyPageTableRecords.mockClear()

    // 下拉框渲染且默认选中主表
    const selector = rendered.container.querySelector(
      'input[data-select="选择数据表"]'
    ) as HTMLInputElement
    expect(selector).toBeTruthy()
    expect(selector.value).toBe('tblMain')

    // 切换子表：带 table_id 重查、回到第一页、恢复默认排序
    act(() => {
      selector.value = 'tblSub'
      selector.dispatchEvent(new Event('change'))
    })
    await settle()

    expect(mocks.getSafetyPageTableRecords).toHaveBeenCalledWith(
      expect.objectContaining({
        tableId: 'tblSub',
        page: 1,
        sortField: '部门/车间',
        sortDirection: 'asc',
      })
    )
  })
})

describe('PageFeishuTable（高级筛选栏与仪表盘联动）', () => {
  const ledgerColumns = [
    { field_id: 'fld-dept', name: '部门/车间', type: 1, kind: 'text', is_primary: false, options: [], editable: true },
    { field_id: 'fld-owner', name: '负责人', type: 11, kind: 'person', is_primary: false, options: [], editable: true },
    { field_id: 'fld-status', name: '关闭状态', type: 3, kind: 'select', is_primary: false, options: [], editable: true },
    { field_id: 'fld-date', name: '检查内容', type: 5, kind: 'date', is_primary: false, options: [], editable: true },
  ]

  function renderLedger() {
    return renderTable({
      initialData: {
        columns: ledgerColumns,
        records: [],
        total: 0,
        page: 1,
        page_size: 20,
        truncated: false,
      },
      filterFields: ['部门/车间', '负责人'],
      filterDateField: '检查内容',
    })
  }

  it('loads filter options from the values endpoint for each field', async () => {
    rendered = renderLedger()
    await settle()

    expect(mocks.getSafetyPageTableFieldValues).toHaveBeenCalledWith({
      pageKey: PAGE_KEY,
      field: '部门/车间',
      tableId: undefined,
    })
    expect(mocks.getSafetyPageTableFieldValues).toHaveBeenCalledWith({
      pageKey: PAGE_KEY,
      field: '负责人',
      tableId: undefined,
    })
  })

  it('syncs field/date filters to both records and stats', async () => {
    rendered = renderLedger()
    await settle()
    // 重查返回同样的台账列，避免默认列集把「检查内容」日期列冲掉
    mocks.getSafetyPageTableRecords.mockResolvedValue({
      code: 200,
      data: {
        columns: ledgerColumns,
        records: [],
        total: 0,
        page: 1,
        page_size: 20,
        truncated: false,
      },
    })
    mocks.getSafetyPageTableRecords.mockClear()
    mocks.getSafetyPageTableStats.mockClear()

    // 选择部门 → 立即重查列表与仪表盘（同条件）
    const deptSelect = rendered.container.querySelector(
      'input[data-select="部门/车间筛选"]'
    ) as HTMLInputElement
    act(() => {
      deptSelect.value = '201一车间'
      deptSelect.dispatchEvent(new Event('change'))
    })
    await settle()

    expect(mocks.getSafetyPageTableRecords).toHaveBeenCalledWith(
      expect.objectContaining({
        conditions: [{ field: '部门/车间', value: '201一车间', op: 'eq' }],
      })
    )
    expect(mocks.getSafetyPageTableStats).toHaveBeenCalledWith(
      expect.objectContaining({
        conditions: [{ field: '部门/车间', value: '201一车间', op: 'eq' }],
      })
    )

    // 时间范围 → gte/lte 一对条件追加
    const range = rendered.container.querySelector(
      'input[data-range-picker="true"]'
    ) as HTMLInputElement
    act(() => {
      range.value = '2026-01-01~2026-03-31'
      range.dispatchEvent(new Event('change'))
    })
    await settle()

    expect(mocks.getSafetyPageTableRecords).toHaveBeenLastCalledWith(
      expect.objectContaining({
        conditions: [
          { field: '部门/车间', value: '201一车间', op: 'eq' },
          { field: '检查内容', value: '2026-01-01', op: 'gte' },
          { field: '检查内容', value: '2026-03-31', op: 'lte' },
        ],
      })
    )

    // 重置筛选 → 条件清空
    act(() => findButton(rendered!.container, '重置筛选')?.click())
    await settle()
    expect(mocks.getSafetyPageTableRecords).toHaveBeenLastCalledWith(
      expect.objectContaining({ conditions: undefined })
    )
  })

  it('keeps the dashboard decoupled from filters on plain pages', async () => {
    rendered = renderTable({ initialData: null })
    await settle()
    mocks.getSafetyPageTableRecords.mockClear()
    mocks.getSafetyPageTableStats.mockClear()

    act(() => findButton(rendered!.container, '刷新')?.click())
    await settle()

    // 未启用高级筛选栏的页面：stats 不带筛选/数据表参数（保持原行为）
    expect(mocks.getSafetyPageTableStats).toHaveBeenCalledWith({
      pageKey: PAGE_KEY,
      groupBy: undefined,
      tableId: undefined,
      keyword: undefined,
      conditions: undefined,
      dueField: undefined,
      closeField: undefined,
    })
  })

  it('applies due drill conditions to the list on first click', async () => {
    const dueColumns = [
      { field_id: 'f1', name: '隐患内容', type: 1, kind: 'text', is_primary: true, options: [], editable: true },
      { field_id: 'f2', name: '目标完成日期', type: 5, kind: 'date', is_primary: false, options: [], editable: true },
      { field_id: 'f3', name: '关闭状态', type: 3, kind: 'select', is_primary: false, options: [], editable: true },
    ]
    mocks.getSafetyPageTableRecords.mockResolvedValue({
      code: 200,
      data: {
        columns: dueColumns,
        records: [],
        total: 0,
        page: 1,
        page_size: 20,
        truncated: false,
      },
    })
    // 到期卡需要 stats 返回 due_summary
    mocks.getSafetyPageTableStats.mockResolvedValue({
      code: 200,
      data: {
        page_key: PAGE_KEY,
        page_name: 'x',
        total: 0,
        groups: [],
        due_summary: { overdue: 6, within_7: 26, within_15: 46, within_30: 49 },
      },
    })
    rendered = renderTable({ dueField: '目标完成日期', initialData: null })
    await settle()
    mocks.getSafetyPageTableRecords.mockClear()

    // 点击「筛选明细」：本次请求即携带 lte + neq 条件（无闭包竞态）
    act(() => findButton(rendered!.container, '筛选明细')?.click())
    await settle()

    const call = mocks.getSafetyPageTableRecords.mock.calls.at(-1)?.[0] as {
      conditions?: Array<{ field: string; value: string; op: string }>
    }
    const ops = call.conditions?.filter((c) => c.op !== 'eq') ?? []
    expect(ops).toHaveLength(2)
    expect(ops[0]).toMatchObject({ field: '目标完成日期', op: 'lte' })
    expect(ops[1]).toMatchObject({ field: '关闭状态', op: 'neq', value: '已关闭' })

    // 取消筛选：条件移除
    act(() => findButton(rendered!.container, '取消筛选')?.click())
    await settle()
    const cleared = mocks.getSafetyPageTableRecords.mock.calls.at(-1)?.[0] as {
      conditions?: unknown[]
    }
    expect(cleared.conditions ?? []).toHaveLength(0)
  })

  it('refalls back stats to dimensions present in the loaded table', async () => {
    // 首轮 stats 因维度缺失失败（不符合项这类结构不同的子表），按实际列回退重查
    mocks.getSafetyPageTableStats
      .mockResolvedValueOnce({ code: 400, data: null })
      .mockResolvedValueOnce({
        code: 200,
        data: {
          page_key: PAGE_KEY,
          page_name: 'x',
          total: 2,
          groups: [
            { field: '整改情况', kind: 'select', mode: 'value', buckets: [{ key: '已整改', count: 2 }] },
          ],
        },
      })
    rendered = renderTable({ initialData: null, statsGroupBy: ['整改情况', '部门/车间'] })
    await settle()

    const calls = mocks.getSafetyPageTableStats.mock.calls
    expect(calls.length).toBeGreaterThanOrEqual(2)
    expect(calls[1]?.[0]).toMatchObject({ groupBy: ['整改情况'] })
  })

  it('creates a record into the active table and reloads from page 1', async () => {
    rendered = renderTable({ allowCreate: true })
    await settle()
    mocks.getSafetyPageTableRecords.mockClear()

    // 无操作权限时新建按钮禁用
    expect(findButton(rendered.container, '新建记录')?.disabled).toBe(false)

    // 打开创建抽屉并填写一个字段后保存
    act(() => findButton(rendered!.container, '新建记录')?.click())
    await settle()
    mocks.form.validateFields.mockResolvedValueOnce({
      整改情况: '未整改',
      值班人员: ['ou_1'],
    })
    act(() => findButton(rendered!.container, '保存')?.click())
    await settle()

    expect(mocks.createSafetyPageTableRecord).toHaveBeenCalledWith({
      pageKey: PAGE_KEY,
      fields: { 整改情况: '未整改', 值班人员: [{ id: 'ou_1' }] },
      tableId: null,
    })
    expect(mocks.message.success).toHaveBeenCalledWith('已新建记录并写入飞书多维表格')
    // 成功后回到第一页刷新列表（列表与仪表盘一起更新）
    expect(mocks.getSafetyPageTableRecords).toHaveBeenCalledWith(
      expect.objectContaining({ page: 1 })
    )
  })

  it('surfaces create failures without reloading', async () => {
    mocks.createSafetyPageTableRecord.mockResolvedValueOnce({
      code: 502,
      message: '写入飞书多维表格失败：字段权限不足',
    })
    rendered = renderTable({ allowCreate: true })
    await settle()

    act(() => findButton(rendered!.container, '新建记录')?.click())
    await settle()
    mocks.getSafetyPageTableRecords.mockClear()
    act(() => findButton(rendered!.container, '保存')?.click())
    await settle()

    expect(mocks.message.error).toHaveBeenCalledWith('写入飞书多维表格失败：字段权限不足')
    expect(mocks.getSafetyPageTableRecords).not.toHaveBeenCalled()
  })
})

describe('PageFeishuTable（statsGroupBy 透传）', () => {  it('passes statsGroupBy to the stats action on reload', async () => {
    rendered = renderTable({ statsGroupBy: ['检查内容'] })
    await settle()
    const refresh = findButton(rendered.container, '刷新')!
    await act(async () => {
      refresh.dispatchEvent(new Event('click', { bubbles: true }))
    })
    await settle()

    const calls = mocks.getSafetyPageTableStats.mock.calls as unknown as Array<
      [{ pageKey: string; groupBy?: string[] }]
    >
    expect(calls.length).toBeGreaterThan(0)
    expect(calls[calls.length - 1][0].groupBy).toEqual(['检查内容'])
  })

  it('omits groupBy when statsGroupBy is not provided', async () => {
    rendered = renderTable()
    await settle()
    const refresh = findButton(rendered.container, '刷新')!
    await act(async () => {
      refresh.dispatchEvent(new Event('click', { bubbles: true }))
    })
    await settle()

    const calls = mocks.getSafetyPageTableStats.mock.calls as unknown as Array<
      [{ pageKey: string; groupBy?: string[] }]
    >
    expect(calls.length).toBeGreaterThan(0)
    expect(calls[calls.length - 1][0].groupBy).toBeUndefined()
  })
})

describe('PageFeishuTable（关键列模式）', () => {
  const changeColumns = [    { field_id: 'f1', name: '申请编号', type: 1, kind: 'text', is_primary: true, options: [], editable: true },
    { field_id: 'f2', name: '发起时间', type: 5, kind: 'date', is_primary: false, options: [], editable: true },
    { field_id: 'f3', name: '变更名称', type: 1, kind: 'text', is_primary: false, options: [], editable: true },
    { field_id: 'f4', name: '变更级别', type: 3, kind: 'select', is_primary: false, options: ['一级', '二级'], editable: true },
    { field_id: 'f5', name: '变更原因', type: 1, kind: 'text', is_primary: false, options: [], editable: true },
    { field_id: 'f6', name: '附件材料', type: 17, kind: 'attachment', is_primary: false, options: [], editable: true },
  ]
  const longReason = '现有反应釜产能不足，需新增一台反应釜并调整对应工艺管线与联锁设定'.repeat(2)
  const changeRows = [
    {
      record_id: 'rec-1',
      fields: {
        申请编号: 'MOC-2026-001',
        发起时间: 1729987200000,
        变更名称: '新增反应釜',
        变更级别: '一级',
        变更原因: longReason,
      },
    },
  ]

  it('shows only the declared preferred columns and hides the rest', async () => {
    rendered = renderTable({
      summarizeColumns: true,
      preferredColumnNames: ['申请编号', '发起时间', '变更名称', '变更级别', '变更原因'],
      initialData: {
        columns: changeColumns,
        records: changeRows,
        total: 1,
        page: 1,
        page_size: 20,
        truncated: false,
      },
    })
    await settle()

    const tds = rendered.container.querySelectorAll(
      'tbody tr[data-row="rec-1"] td'
    )
    // 只渲染声明的 5 个关键列（按声明顺序），附件列不在表格里
    expect(tds.length).toBe(5)
    expect(tds[0]?.textContent).toContain('MOC-2026-001')
    expect(tds[3]?.textContent).toContain('一级')
    expect(rendered.container.innerHTML).not.toContain('tok-')
    // 未命中的字段收进详情：提示剩余字段数
    expect(rendered.container.innerHTML).toContain('其余 1 个字段')
  })

  it('wraps long-text preferred columns instead of dropping them', async () => {
    rendered = renderTable({
      summarizeColumns: true,
      preferredColumnNames: ['申请编号', '变更原因'],
      initialData: {
        columns: changeColumns,
        records: changeRows,
        total: 1,
        page: 1,
        page_size: 20,
        truncated: false,
      },
    })
    await settle()

    const html = rendered.container.innerHTML
    // 自动摘要会丢弃长文本列；关键列模式下按声明保留并换行渲染
    expect(html).toContain(longReason)
    expect(html).toContain('pre-wrap')
  })

  it('falls back to auto summary when preferred names mostly miss', async () => {    const manyColumns = [
      ...Array.from({ length: 12 }, (_, index) => ({
        field_id: `fld-biz${index}`,
        name: `业务列${index + 1}`,
        type: 1,
        kind: 'text',
        is_primary: false,
        options: [],
        editable: true,
      })),
    ]
    rendered = renderTable({
      summarizeColumns: true,
      preferredColumnNames: ['业务列1', '已改名A', '已改名B', '已改名C', '已改名D'],
      initialData: {
        columns: manyColumns,
        records: [{ record_id: 'rec-1', fields: { 业务列1: 'A' } }],
        total: 1,
        page: 1,
        page_size: 20,
        truncated: false,
      },
    })
    await settle()

    // 命中 1 列 < 3：回退自动摘要（10 列），而不是只渲染零星关键列
    expect(
      rendered.container.querySelectorAll('tbody tr[data-row="rec-1"] td')
        .length
    ).toBe(10)
    expect(rendered.container.innerHTML).toContain('其余 2 个字段')
  })
})

describe('PageFeishuTable（新增跳转链接）', () => {
  it('renders the create button as an external jump link when createUrl is set', async () => {
    rendered = renderTable({
      summarizeColumns: true,
      allowCreate: true,
      createUrl: 'https://applink.feishu.cn/T9aVmYNY9oKR',
    })
    await settle()

    const link = rendered.container.querySelector(
      'a[href="https://applink.feishu.cn/T9aVmYNY9oKR"]'
    ) as HTMLAnchorElement
    expect(link).toBeTruthy()
    expect(link.target).toBe('_blank')
    expect(link.textContent).toContain('新增')
    // 跳转模式不打开站内新建抽屉
    expect(rendered.container.innerHTML).not.toContain('新记录将写入当前选中的数据表')
  })

  it('keeps the in-page create button when no createUrl is provided', async () => {
    rendered = renderTable({ allowCreate: true })
    await settle()

    expect(
      rendered.container.querySelector(
        'a[href="https://applink.feishu.cn/T9aVmYNY9oKR"]'
      )
    ).toBeNull()
    expect(findButton(rendered.container, '新建记录')).toBeTruthy()
  })
})

describe('PageFeishuTable（列宽）', () => {
  it('pins narrow-content columns to compact widths in summary mode', async () => {
    const mixedColumns = [
      { field_id: 'f1', name: '申请编号', type: 1, kind: 'text', is_primary: true, options: [], editable: true },
      { field_id: 'f2', name: '申请状态', type: 3, kind: 'select', is_primary: false, options: ['已通过'], editable: true },
      { field_id: 'f3', name: '发起时间', type: 5, kind: 'date', is_primary: false, options: [], editable: true },
      { field_id: 'f4', name: '变更申请人', type: 11, kind: 'person', is_primary: false, options: [], editable: true },
      { field_id: 'f5', name: '变更名称', type: 1, kind: 'text', is_primary: false, options: [], editable: true },
    ]
    rendered = renderTable({
      summarizeColumns: true,
      initialData: {
        columns: mixedColumns,
        records: [{ record_id: 'rec-1', fields: {} }],
        total: 1,
        page: 1,
        page_size: 20,
        truncated: false,
      },
    })
    await settle()

    const widths = new Map(
      mocks.capturedTableColumns.map((column: Record<string, unknown>) => [
        (column.dataIndex as string[])[1],
        column.width as number | undefined,
      ])
    )
    // 窄内容列固定紧凑宽度，剩余空间留给名称等文本列
    expect(widths.get('申请状态')).toBe(110)
    expect(widths.get('发起时间')).toBe(112)
    expect(widths.get('变更申请人')).toBe(110)
    // 文本列不设固定宽度，自动吸收剩余空间
    expect(widths.get('申请编号')).toBeUndefined()
    expect(widths.get('变更名称')).toBeUndefined()
  })

  it('危化品镜像页可切换「只看超储」并按行标记超储样式', async () => {
    const base = okRecords()
    mocks.getSafetyPageTableRecords.mockResolvedValue({
      ...base,
      data: {
        ...base.data,
        over_limit_fields: { quantity_field: '库存数量', limit_field: '存储上限' },
        records: [
          { record_id: 'rec-1', fields: {}, over_limit: true },
          { record_id: 'rec-2', fields: {} },
        ],
      },
    })
    rendered = renderTable({
      pageKey: 'safety:site-mgmt:hazchem-msds',
      pageName: '危化品统计表（车间库存/超储）',
      initialData: null,
    })
    await settle()

    const toggle = findButton(rendered.container, '只看超储')
    expect(toggle).toBeDefined()
    act(() => toggle!.click())
    await settle()
    expect(mocks.getSafetyPageTableRecords).toHaveBeenLastCalledWith(
      expect.objectContaining({ overLimitOnly: true }),
    )
    const highlighted = rendered.container.querySelectorAll('tr.bg-red-50')
    expect(highlighted.length).toBe(1)
    expect(highlighted[0].getAttribute('data-row')).toBe('rec-1')
  })
})
