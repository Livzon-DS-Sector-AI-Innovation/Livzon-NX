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
  updateSafetyPageTableRecord: vi.fn(),
  uploadSafetyPageTableAttachment: vi.fn(),
  statsSelect: vi.fn(),
}))

vi.mock('@/actions/safety', () => ({
  getSafetyPageTableRecords: mocks.getSafetyPageTableRecords,
  getSafetyPageTableStats: mocks.getSafetyPageTableStats,
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
  }: {
    columns?: Column[]
    dataSource?: Row[]
    onChange?: (pagination: { current?: number; pageSize?: number }) => void
    onRow?: (row: Row) => { onClick?: () => void }
  }) =>
    createElement(
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
    DatePicker: Box,
    Drawer: Box,
    Form: Object.assign(({ children }: AnyProps) => createElement('form', null, children as ReactNode), {
      Item: Box,
      useForm: () => [mocks.form],
    }),
    Input,
    InputNumber: Box,
    Select: Box,
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
  mocks.updateSafetyPageTableRecord.mockResolvedValue({
    code: 200,
    data: rows[0],
  })
  mocks.uploadSafetyPageTableAttachment.mockResolvedValue({
    code: 200,
    data: { attachments: [{ file_token: 'tok-new', name: 'photo.png' }] },
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
      `/api/v1/safety/page-tables/${encodeURIComponent(PAGE_KEY)}/records/rec-9/attachments/${encodeURIComponent('照片')}/tok-9/content`
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

    expect(rendered.container.innerHTML).toContain('仅显示前 2000 条')
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