/* @vitest-environment happy-dom */

import { act, createElement, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import dayjs from 'dayjs'
import { useAuthStore } from '@/stores/auth'

const mocks = vi.hoisted(() => ({
  message: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
  hasAny: vi.fn().mockReturnValue(true),
  router: { push: vi.fn() },
  searchParams: new URLSearchParams(
    'keyword=%E5%88%86%E6%9E%90&date_field=%E5%85%A5%E5%BA%93%E6%97%A5%E6%9C%9F&date_filter_type=eq&start_date=2026-08-25&quality_status=%E5%90%88%E6%A0%BC&filters=%5B%7B%22field%22%3A%22%E7%89%A9%E6%96%99%E5%90%8D%E7%A7%B0%22%2C%22operator%22%3A%22contains%22%2C%22value%22%3A%22%E6%A0%87%E7%AD%BE%22%7D%5D',
  ),
  fetchWarehouseMaterialPage: vi.fn(),
  fetchWarehouseRecordDetail: vi.fn(),
  updateWarehouseRecordAction: vi.fn(),
  deleteWarehouseRecordAction: vi.fn(),
}))

vi.mock('next/navigation', () => ({
  usePathname: () => '/warehouse/materials/raw-summary',
  useRouter: () => mocks.router,
  useSearchParams: () => mocks.searchParams,
}))
vi.mock('@/hooks/usePermission', () => ({ usePermission: () => ({ hasAny: mocks.hasAny }) }))
vi.mock('@/lib/api/client/warehouse', () => ({
  fetchWarehouseMaterialPage: mocks.fetchWarehouseMaterialPage,
  fetchWarehouseRecordDetail: mocks.fetchWarehouseRecordDetail,
}))
vi.mock('@/actions/warehouse', () => ({
  deleteWarehouseRecordAction: mocks.deleteWarehouseRecordAction,
  updateWarehouseRecordAction: mocks.updateWarehouseRecordAction,
}))
vi.mock('@ant-design/icons', () => {
  const Icon = () => null
  return {
    ClockCircleOutlined: Icon,
    DatabaseOutlined: Icon,
    ExportOutlined: Icon,
    EyeOutlined: Icon,
    ImportOutlined: Icon,
    ReloadOutlined: Icon,
  }
})
vi.mock('antd', async () => {
  const React = await import('react')
  const Wrapper = ({ children, ...props }: { children?: ReactNode } & Record<string, unknown>) =>
    React.createElement('div', props, children)
  const Button = ({ children, onClick, htmlType, loading }: { children?: ReactNode; onClick?: () => void; htmlType?: string; loading?: boolean }) =>
    React.createElement('button', { type: htmlType === 'submit' ? 'submit' : 'button', disabled: loading, onClick }, children)
  const Input = ({ value, onChange, placeholder }: { value?: unknown; onChange?: (event: { target: { value: string } }) => void; placeholder?: string }) =>
    React.createElement('input', { value: value ?? '', placeholder, onChange: (event: Event) => onChange?.({ target: { value: (event.target as HTMLInputElement).value } }) })
  const TextArea = ({ value, onChange, placeholder }: { value?: unknown; onChange?: (event: { target: { value: string } }) => void; placeholder?: string }) =>
    React.createElement('textarea', { value: value ?? '', placeholder, onChange: (event: Event) => onChange?.({ target: { value: (event.target as HTMLTextAreaElement).value } }) })
  Input.TextArea = TextArea
  const Select = ({ value, options = [], onChange, mode, placeholder }: { value?: unknown; options?: Array<{ label: string; value: string }>; onChange?: (value: unknown) => void; mode?: string; placeholder?: string }) =>
    React.createElement('select', {
      value: Array.isArray(value) ? value[0] ?? '' : value ?? '',
      multiple: mode === 'multiple',
      'aria-label': placeholder,
      onChange: (event: Event) => onChange?.((event.target as HTMLSelectElement).value),
    }, [React.createElement('option', { key: 'empty', value: '' }, placeholder ?? ''), ...options.map((option) => React.createElement('option', { key: option.value, value: option.value }, option.label))])
  const DatePicker = ({ value, onChange, placeholder }: { value?: unknown; onChange?: (value: unknown) => void; placeholder?: string }) =>
    React.createElement('input', { type: 'date', value: value && typeof value === 'object' && 'format' in value ? (value as { format: (format: string) => string }).format('YYYY-MM-DD') : '', placeholder, onChange: () => onChange?.(null) })
  const InputNumber = ({ value, onChange }: { value?: unknown; onChange?: (value: unknown) => void }) =>
    React.createElement('input', { type: 'number', value: value ?? '', onChange: () => onChange?.(1) })
  const Switch = ({ checked, onChange }: { checked?: boolean; onChange?: (value: boolean) => void }) =>
    React.createElement('input', { type: 'checkbox', checked: Boolean(checked), onChange: (event: Event) => onChange?.((event.target as HTMLInputElement).checked) })
  const Card = ({ children, title, extra, onClick, className }: { children?: ReactNode; title?: ReactNode; extra?: ReactNode; onClick?: () => void; className?: string }) =>
    React.createElement('section', { className, onClick }, [title, extra, children])
  const Modal = ({ open, children, footer, title, onCancel }: { open?: boolean; children?: ReactNode; footer?: ReactNode; title?: ReactNode; onCancel?: () => void }) =>
    open ? React.createElement('div', { role: 'dialog' }, [React.createElement('h2', { key: 'title' }, title), React.createElement('button', { key: 'cancel', onClick: onCancel }, '关闭'), children, footer]) : null
  const Table = ({ columns = [], dataSource = [], rowKey, locale }: { columns?: Array<{ title?: ReactNode; dataIndex?: string; render?: (value: unknown, record: Record<string, unknown>) => ReactNode }>; dataSource?: Array<Record<string, unknown>>; rowKey?: (record: Record<string, unknown>) => string; locale?: { emptyText?: ReactNode } }) => {
    const rows = dataSource.length
      ? dataSource.map((record, rowIndex) => React.createElement(
        'tr',
        { key: rowKey?.(record) ?? rowIndex },
        columns.map((column, index) => React.createElement(
          'td',
          { key: `${index}` },
          column.render
            ? column.render(column.dataIndex ? record[column.dataIndex] : undefined, record)
            : column.dataIndex
              ? String(record[column.dataIndex] ?? '')
              : '',
        )),
      ))
      : React.createElement('tr', { key: 'empty' }, React.createElement('td', { colSpan: columns.length }, locale?.emptyText))
    return React.createElement('table', { 'data-row-count': dataSource.length }, [
      React.createElement('thead', { key: 'head' }, React.createElement('tr', null, columns.map((column, index) => React.createElement('th', { key: `${String(column.title)}-${index}` }, column.title)))),
      React.createElement('tbody', { key: 'body' }, rows),
    ])
  }
  const Descriptions = ({ children }: { children?: ReactNode }) => React.createElement('dl', null, children)
  const DescriptionItem = ({ children, label }: { children?: ReactNode; label?: ReactNode }) => React.createElement('div', null, [React.createElement('dt', { key: 'label' }, label), React.createElement('dd', { key: 'value' }, children)])
  Descriptions.Item = DescriptionItem
  const Empty = ({ description }: { description?: ReactNode }) => React.createElement('span', null, description)
  Empty.PRESENTED_IMAGE_SIMPLE = null
  const Avatar = ({ children }: { children?: ReactNode }) => React.createElement('span', null, children)
  const Tag = ({ children }: { children?: ReactNode }) => React.createElement('span', null, children)
  const Statistic = ({ title, value, prefix }: { title?: ReactNode; value?: ReactNode; prefix?: ReactNode }) => React.createElement('div', null, [title, prefix, value])
  const Popconfirm = ({ children, onConfirm, okText }: { children?: ReactNode; onConfirm?: () => void; okText?: string }) => {
    const [open, setOpen] = React.useState(false)
    return React.createElement('div', null,
      React.createElement('span', { onClick: () => setOpen(true) }, children),
      open ? React.createElement('button', { onClick: () => { onConfirm?.(); setOpen(false) } }, `确认${okText ?? ''}`) : null,
    )
  }
  return {
    App: { useApp: () => ({ message: mocks.message }) },
    Alert: ({ title, description }: { title?: ReactNode; description?: ReactNode }) => React.createElement('div', { role: 'alert' }, title, description),
    Avatar,
    Button,
    Card,
    DatePicker,
    Descriptions,
    Empty,
    Input,
    InputNumber,
    Modal,
    Popconfirm,
    Select,
    Space: Wrapper,
    Spin: Wrapper,
    Statistic,
    Switch,
    Table,
    Tag,
  }
})

import {
  WarehouseFeishuTablePage,
  buildAdvancedFilterLabel,
  buildDateFilterLabel,
  buildGroupedRows,
  buildVisiblePageData,
  formatDateValue,
  formatDetailDisplayValue,
  formatSyncTime,
  getUniqueOptions,
  isDateLikeColumn,
  parseAdvancedFilters,
  resolveDateFilterRange,
  resolveInoutLinks,
} from './WarehouseFeishuTablePage'

const tableData = {
  page_key: 'raw-summary',
  page_title: '原辅料库存汇总',
  table_name: '原辅料库存',
  base_name: '仓储',
  source: 'feishu_bitable',
  last_sync_time: '2026-08-25T08:00:00Z',
  page: 1,
  page_size: 50,
  total: 2,
  columns: [
    { key: '使用产品/类别', title: '使用产品/类别', field_type: 1 },
    { key: '物料名称', title: '物料名称', field_type: 1 },
    { key: '入库日期', title: '入库日期', field_type: 5 },
    { key: '质量状态', title: '质量状态', field_type: 1 },
    { key: '预警', title: '预警', field_type: 1 },
    { key: '领料人', title: '领料人', field_type: 11 },
    { key: '是否关键', title: '是否关键', field_type: 7 },
    { key: '父记录', title: '父记录', field_type: 1 },
  ],
  rows: [
    {
      __record_id: 'row-1',
      '使用产品/类别': '阿莫西林',
      物料名称: '标签纸',
      入库日期: '2026-08-25',
      质量状态: '合格',
      预警: '库存不足',
      领料人: [{ name: '张三', id: 'user-1' }],
      是否关键: true,
      父记录: 'hidden',
    },
    {
      __record_id: 'row-2',
      '使用产品/类别': '阿莫西林',
      物料名称: '包装袋',
      入库日期: 1_756_080_000_000,
      质量状态: '不合格',
      预警: '库存严重不足',
      领料人: '李四',
      是否关键: false,
      父记录: 'hidden',
    },
  ],
  stats: {
    severe_low_stock_count: 1,
    low_stock_count: 1,
    failed_count: 1,
    pending_count: 1,
    qualified_count: 1,
    month_count: 2,
    today_count: 1,
    amount_total: 120,
    stock_count: 2,
  },
} as never

const detail = {
  record_id: 'row-1',
  fields: [
    { field_name: '只读人', value: [{ name: '张三' }], field_type: 11, readonly: true },
    { field_name: '备注', value: '旧备注', field_type: 1, editable: true },
    { field_name: '数量', value: 2, field_type: 2, editable: true },
    { field_name: '状态', value: '合格', field_type: 3, options: [{ name: '合格' }, { name: '待验' }], editable: true },
    { field_name: '标签', value: 'A,B', field_type: 4, options: [{ name: 'A' }, { name: 'B' }], editable: true },
    { field_name: '日期', value: '2026-08-25', field_type: 5, editable: true },
    { field_name: '开关', value: true, field_type: 7, editable: true },
    { field_name: '其他', value: '文本', field_type: 99, editable: true },
    { field_name: '仅查看', value: false, field_type: 1, view_only: true },
    { field_name: '父记录', value: 'hidden', field_type: 1, editable: true },
  ],
} as never

describe('WarehouseFeishuTablePage', () => {
  let container: HTMLDivElement
  let root: Root
  let client: QueryClient

  beforeEach(() => {
    vi.clearAllMocks()
    useAuthStore.getState().clearUser()
    mocks.hasAny.mockReturnValue(true)
    mocks.fetchWarehouseMaterialPage.mockImplementation(async () => tableData)
    mocks.fetchWarehouseRecordDetail.mockResolvedValue(detail)
    mocks.updateWarehouseRecordAction.mockResolvedValue({ code: 200 })
    mocks.deleteWarehouseRecordAction.mockResolvedValue({ code: 200 })
    localStorage.clear()
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  })

  afterEach(() => {
    act(() => root.unmount())
    useAuthStore.getState().clearUser()
    client.clear()
    container.remove()
    vi.restoreAllMocks()
  })

  async function mount(data = tableData, pageKey = 'raw-summary') {
    await act(async () => {
      root.render(createElement(
        QueryClientProvider,
        { client },
        createElement(WarehouseFeishuTablePage, { data, pageKey }),
      ))
      await Promise.resolve()
      await Promise.resolve()
    })
  }

  function authorize(level: 'access' | 'query' | 'operate', actions: string[] = []) {
    useAuthStore.getState().setUser({
      id: 'page-user', name: '页面用户', permissions: ['*'],
      page_permission_rollouts: { warehouse: 'enforced' },
      page_permissions: [{
        page_key: 'warehouse:materials:raw-summary', module_code: 'warehouse',
        permissions: level === 'operate' ? ['access', 'query', 'operate'] : level === 'query' ? ['access', 'query'] : ['access'],
        sensitive_actions: actions, data_scope: { scope_type: 'not_applicable' }, source: 'user',
      }],
    })
  }

  it('does not fetch or show records with access-only permission', async () => {
    authorize('access')
    await mount()
    expect(container.textContent).toContain('此页面未获得查询数据权限')
    expect(container.querySelector('table')).toBeNull()
    expect(mocks.fetchWarehouseMaterialPage).not.toHaveBeenCalled()
  })

  it.each(['query', 'operate'] as const)('uses page %s permission instead of legacy wildcard and separates delete', async (level) => {
    authorize(level)
    await mount()
    const button = (label: string) => Array.from(container.querySelectorAll('button')).find((item) => item.textContent === label)
    await act(async () => button('详情')?.click())
    expect(container.textContent).toContain('记录详情')
    expect(Boolean(button('编辑'))).toBe(level === 'operate')
    expect(button('删除记录')).toBeUndefined()
    expect(button('同步最新数据')).toBeUndefined()
    await act(async () => button('刷新')?.click())
    expect(mocks.fetchWarehouseMaterialPage).toHaveBeenLastCalledWith('raw-summary', expect.objectContaining({ force: false }), 60000)
  })

  it('requires explicit confirmation before authorized remote synchronization', async () => {
    authorize('operate', ['sync_config', 'delete'])
    await mount()
    const button = (label: string) => Array.from(container.querySelectorAll('button')).find((item) => item.textContent === label)
    mocks.fetchWarehouseMaterialPage.mockClear()
    await act(async () => button('同步最新数据')?.click())
    expect(mocks.fetchWarehouseMaterialPage).not.toHaveBeenCalled()
    await act(async () => button('确认同步')?.click())
    expect(mocks.fetchWarehouseMaterialPage).toHaveBeenCalledWith('raw-summary', expect.objectContaining({ force: true }), 60000)
    await act(async () => button('详情')?.click())
    expect(button('删除记录')).toBeDefined()
  })

  it('covers warehouse filter, projection, grouping, and display helpers', () => {
    expect(resolveInoutLinks('raw-ledger')?.inbound).toContain('feishu.cn')
    expect(resolveInoutLinks('unknown')).toBeNull()
    expect(isDateLikeColumn('入库日期')).toBe(true)
    expect(isDateLikeColumn('物料名称')).toBe(false)
    expect(formatDateValue(null as never)).toBeNull()
    expect(formatDateValue(1_756_080_000_000)).toMatch(/^2025-/)
    expect(formatDateValue('1756080000')).toMatch(/^2025-/)
    expect(formatDateValue('not-a-date')).toBe('not-a-date')

    const selected = dayjs('2026-08-25')
    expect(resolveDateFilterRange('eq', selected)).toEqual({ startDate: '2026-08-25', endDate: '2026-08-25' })
    expect(resolveDateFilterRange('gt', selected).endDate).toBe('')
    expect(resolveDateFilterRange('lt', selected).startDate).toBe('')
    expect(resolveDateFilterRange('this_week', null).startDate).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    expect(resolveDateFilterRange('last_week', null).endDate).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    expect(resolveDateFilterRange('this_month', null).startDate).toMatch(/^\d{4}-\d{2}-01$/)
    expect(resolveDateFilterRange('last_month', null).endDate).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    expect(buildDateFilterLabel('', '', '')).toBe('')
    expect(buildDateFilterLabel('eq', '2026-08-25', '')).toContain('等于')
    expect(buildDateFilterLabel('gt', '2026-08-25', '')).toContain('大于')
    expect(buildDateFilterLabel('lt', '', '2026-08-25')).toContain('小于')
    expect(buildDateFilterLabel('between', '', '')).toContain('between')

    const sourceData = {
      columns: [
        { key: '入库日期', title: '入库日期', field_type: 5 },
        { key: '物料名称', title: '物料名称', field_type: 1 },
        { key: '隐藏字段', title: '隐藏字段', field_type: 1 },
      ],
      rows: [
        { __record_id: 'r1', '入库日期': 1_756_080_000_000, '物料名称': 'A', '隐藏字段': 'x' },
        { __record_id: 'r2', '入库日期': 1_756_000_000_000, '物料名称': 'B', '隐藏字段': 'y' },
      ],
    } as never
    const projection = buildVisiblePageData('unknown-page', sourceData)
    expect(projection.columns.map((column) => column.key)).toContain('物料名称')
    expect(projection.rows[0]['入库日期']).toMatch(/^2025-/)
    const ruleProjection = buildVisiblePageData('raw-summary', {
      columns: [{ key: '物料名称', title: '物料名称', field_type: 1 }],
      rows: [{ __record_id: 'r3', 物料名称: 'C' }],
    } as never)
    expect(ruleProjection.rows[0].__record_id).toBe('r3')

    expect(parseAdvancedFilters(null)).toEqual([])
    expect(parseAdvancedFilters('invalid-json')).toEqual([])
    expect(parseAdvancedFilters(JSON.stringify({ field: '状态' }))).toEqual([])
    expect(parseAdvancedFilters(JSON.stringify([{ field: '状态', operator: 'between', value: 'A', value_to: 'B' }]))).toHaveLength(1)
    expect(getUniqueOptions([{ a: ' B ', b: 'A' }, { a: '', b: null }] as never, ['a', 'b'])).toEqual([
      { label: 'A', value: 'A' },
      { label: 'B', value: 'B' },
    ])
    expect(buildAdvancedFilterLabel({ field: '状态', operator: 'empty', value: '' })).toContain('为空')
    expect(buildAdvancedFilterLabel({ field: '金额', operator: 'between', value: '1', value_to: '9' })).toContain('1')
    expect(buildAdvancedFilterLabel({ field: '状态', operator: 'contains', value: '' })).toContain('-')

    const grouped = buildGroupedRows([
      { __record_id: 'g1', 入库日期: '2026-08-25', 库区: '一号库' },
      { __record_id: 'g2', 入库日期: '2026-08-24', 库区: '' },
    ] as never, ['入库日期', '库区'])
    expect(grouped.filter((row) => '__group_row' in row)).toHaveLength(4)
    expect(buildGroupedRows([{ __record_id: 'plain' }] as never, [])).toEqual([{ __record_id: 'plain' }])
    expect(formatDetailDisplayValue({ field_name: '空', value: null } as never)).toBe('-')
    expect(formatDetailDisplayValue({ field_name: '列表', value: ['A', { name: 'B' }, { text: 'C' }, { id: 'D' }] } as never)).toBe('A、B、C、D')
    expect(formatDetailDisplayValue({ field_name: '开关', value: true } as never)).toBe('是')
    expect(formatSyncTime(undefined)).toBe('-')
    expect(formatSyncTime('2026-08-25T08:00:00Z')).toContain('2026-08-25')
  })

  it('keeps group row keys unique when the same subgroup value appears under different parents', () => {
    const grouped = buildGroupedRows(
      [
        { __record_id: 'a1', 库区: '一号库', 物料名称: '磷酸氢二钾' },
        { __record_id: 'a2', 库区: '二号库', 物料名称: '磷酸氢二钾' },
      ] as never,
      ['库区', '物料名称']
    )
    const keys = grouped.map((row) =>
      '__group_row' in row ? `group-${JSON.stringify(row.__group_path)}` : row.__record_id
    )
    expect(new Set(keys).size).toBe(keys.length)
    // 不同父组下的同名二级分组应各自独立存在且 key 不同
    expect(
      grouped.filter(
        (row) => '__group_row' in row && row.__group_level === 1 && row.__group_value === '磷酸氢二钾'
      )
    ).toHaveLength(2)
  })

  it('renders filters, stats, person/status cells, details, edit, save, and delete flows', async () => {
    await mount(tableData, 'product-summary')

    expect(container.textContent).toContain('原辅料库存汇总')
    expect(container.textContent).toContain('关键字：分析')
    expect(container.textContent).toContain('库存严重不足')
    expect(container.textContent).toContain('张三')
    expect(container.textContent).toContain('李四')
    expect(container.textContent).toContain('不合格')

    const buttons = () => Array.from(container.querySelectorAll('button'))
    const findButton = (text: string) => buttons().find((button) => button.textContent?.includes(text))
    await act(async () => findButton('查询')?.click())
    expect(mocks.router.push).toHaveBeenCalled()
    await act(async () => findButton('重置')?.click())

    await act(async () => findButton('详情')?.click())
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(container.textContent).toContain('记录详情')
    expect(container.textContent).toContain('只读人')
    expect(container.textContent).toContain('仅查看')

    await act(async () => findButton('编辑')?.click())
    expect(container.querySelector('textarea')).not.toBeNull()
    await act(async () => findButton('保存修改')?.click())
    expect(mocks.updateWarehouseRecordAction).toHaveBeenCalledWith('product-summary', 'row-1', expect.any(Object))

    const severeCard = Array.from(container.querySelectorAll('section')).find((section) => section.textContent?.includes('库存严重不足'))
    await act(async () => severeCard?.dispatchEvent(new MouseEvent('click', { bubbles: true })))
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(container.textContent).toContain('库存严重不足明细')
    expect(mocks.fetchWarehouseMaterialPage).toHaveBeenCalled()
  })

  it('renders snapshot/no-permission and error branches without exposing write controls', async () => {
    mocks.hasAny.mockReturnValue(false)
    mocks.fetchWarehouseRecordDetail.mockRejectedValue(new Error('detail unavailable'))
    const snapshot = { ...(tableData as Record<string, unknown>), source: 'local_snapshot', rows: [], total: 0, stats: undefined } as never
    mocks.fetchWarehouseMaterialPage.mockImplementation(async () => snapshot)
    await mount(snapshot, 'qualified-suppliers')

    expect(container.textContent).toContain('本地快照')
    expect(container.textContent).toContain('未找到符合当前筛选条件的数据')
    expect(container.textContent).not.toContain('库存严重不足')
    expect(container.textContent).not.toContain('编辑')
    expect(container.textContent).not.toContain('删除记录')

    const detailButton = Array.from(container.querySelectorAll('button')).find((button) => button.textContent?.includes('详情'))
    expect(detailButton).toBeUndefined()
    expect(mocks.fetchWarehouseRecordDetail).not.toHaveBeenCalled()
  })

  it('covers inbound and hardware page rules, date filters, grouping, and failed detail loading', async () => {
    mocks.searchParams = new URLSearchParams()
    const richData = {
      ...(tableData as Record<string, unknown>),
      page_key: 'inbound-ledger',
      page_title: '入库登记',
      table_name: '入库登记台账',
      columns: [
        { key: '物料名称', title: '物料名称', field_type: 1 },
        { key: '产品', title: '产品', field_type: 3, options: [{ name: '产品A' }] },
        { key: '库区', title: '库区', field_type: 1 },
        { key: '入库日期', title: '入库日期', field_type: 5 },
        { key: '金额', title: '金额', field_type: 2 },
        { key: '负责人', title: '负责人', field_type: 11 },
      ],
      rows: [
        { __record_id: 'in-1', 物料名称: '原料A', 产品: '产品A', 库区: '一号库', 入库日期: '2026-08-25', 金额: 12, 负责人: [{ name: '王五', id: 'u-5' }] },
        { __record_id: 'in-2', 物料名称: '原料B', 产品: '', 库区: '二号库', 入库日期: '2026-08-24', 金额: 0, 负责人: { name: '赵六' } },
      ],
      stats: { month_count: 2, today_count: 1, amount_total: 12, stock_count: 2 },
    }
    mocks.fetchWarehouseMaterialPage.mockResolvedValue(richData)
    await mount(richData as never, 'inbound-ledger')
    expect(container.textContent).toContain('入库登记台账')
    expect(container.textContent).toContain('原料A')

    const findButton = (text: string) => Array.from(container.querySelectorAll('button')).find((button) => button.textContent?.includes(text))
    await act(async () => findButton('高级筛选')?.click())
    await act(async () => findButton('新增条件')?.click())
    const selects = Array.from(container.querySelectorAll('select'))
    const operator = selects.at(-1)
    if (operator) {
      operator.value = 'between'
      operator.dispatchEvent(new Event('change', { bubbles: true }))
    }
    await act(async () => findButton('查询')?.click())
    await act(async () => findButton('重置')?.click())

    mocks.fetchWarehouseRecordDetail.mockRejectedValueOnce(new Error('明细服务不可用'))
    await act(async () => findButton('详情')?.click())
    await act(async () => { await Promise.resolve(); await Promise.resolve() })
    expect(mocks.message.error).toHaveBeenCalledWith(expect.stringContaining('详情加载失败'))
  })

  it('renders product inbound detail with projected columns, date-desc order, and 新增 button', async () => {
    mocks.searchParams = new URLSearchParams()
    expect(resolveInoutLinks('product-inbound-detail')?.inboundLabel).toBe('新增')

    const detailData = {
      page_key: 'product-inbound-detail',
      page_title: '成品入库明细',
      table_name: '成品入库明细',
      source: 'feishu_bitable',
      last_sync_time: '2026-08-25T08:00:00Z',
      page: 1,
      page_size: 200,
      total: 2,
      columns: [
        { key: '入库日期', title: '入库日期', field_type: 5 },
        { key: '产品名称', title: '产品名称', field_type: 1 },
        { key: '包装规格', title: '包装规格', field_type: 1 },
        { key: '对应前台批号', title: '对应前台批号', field_type: 1 },
        { key: '入库标签批号', title: '入库标签批号', field_type: 1 },
        { key: '入库量', title: '入库量', field_type: 2 },
        { key: '客户', title: '客户', field_type: 1 },
        { key: '包装桶UN信息', title: '包装桶UN信息', field_type: 1 },
        { key: '备注（填写实物批号）', title: '备注（填写实物批号）', field_type: 1 },
        { key: '入库车间', title: '入库车间', field_type: 3, options: [{ name: '201一车间' }] },
        { key: 'QC确认人', title: 'QC确认人', field_type: 11 },
        { key: '入库确认', title: '入库确认', field_type: 1 },
        { key: '仓库确认人', title: '仓库确认人', field_type: 11 },
      ],
      rows: [
        {
          __record_id: 'pd-1',
          入库日期: 1_756_080_000_000,
          产品名称: 'L-苯丙氨酸',
          包装规格: '25kg/桶',
          对应前台批号: 'B-1024',
          入库标签批号: 'R-1024',
          入库量: 300,
          客户: '客户甲',
          包装桶UN信息: 'UN1A/Y1.4/150',
          '备注（填写实物批号）': '',
          入库车间: '201一车间',
          QC确认人: [{ name: '张三' }],
          入库确认: '已确认',
          仓库确认人: [{ name: '李四' }],
        },
        {
          __record_id: 'pd-2',
          入库日期: 1_757_080_000_000,
          产品名称: 'L-色氨酸',
          包装规格: '10kg/桶',
          对应前台批号: 'B-1026',
          入库标签批号: 'R-1026',
          入库量: 150,
          客户: '客户乙',
          包装桶UN信息: 'UN1A/Y1.4/100',
          '备注（填写实物批号）': '实物批号备注',
          入库车间: '201一车间',
          QC确认人: [{ name: '王五' }],
          入库确认: '待确认',
          仓库确认人: [{ name: '赵六' }],
        },
      ],
      stats: { month_count: 2, today_count: 1, stock_count: 2 },
    } as never
    mocks.fetchWarehouseMaterialPage.mockResolvedValue(detailData)
    await mount(detailData, 'product-inbound-detail')

    const headerText = Array.from(container.querySelectorAll('thead th'))
      .map((th) => th.textContent ?? '')
      .join('|')
    expect(headerText).toContain('入库日期')
    expect(headerText).toContain('包装桶UN信息')
    // 列表不展示低频字段（QC确认人、入库确认、仓库确认人在详情弹窗查看）
    expect(headerText).not.toContain('QC确认人')
    expect(headerText).not.toContain('入库确认')
    expect(headerText).not.toContain('仓库确认人')
    expect(container.textContent).not.toContain('张三')

    // 按入库日期倒序：最新记录（2026-08-26，pd-2）在第一行业务行
    const bodyRows = Array.from(container.querySelectorAll('tbody tr'))
    const firstBusinessRow = bodyRows.find((row) => row.textContent?.includes('L-色氨酸'))
    expect(firstBusinessRow).toBeDefined()
    const firstRowIndex = bodyRows.indexOf(firstBusinessRow!)
    const laterRow = bodyRows.find((row) => row.textContent?.includes('L-苯丙氨酸'))
    expect(laterRow).toBeDefined()
    expect(firstRowIndex).toBeLessThan(bodyRows.indexOf(laterRow!))

    // 入库登记按钮按 inboundLabel 显示为「新增」
    const buttons = Array.from(container.querySelectorAll('button'))
    expect(buttons.some((button) => button.textContent === '新增')).toBe(true)
    expect(buttons.some((button) => button.textContent === '入库登记')).toBe(false)
  })
})
