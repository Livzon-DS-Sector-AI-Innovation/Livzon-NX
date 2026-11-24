/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import type { ReactElement, ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const navigation = vi.hoisted(() => ({ replace: vi.fn() }))
const mappedApi = vi.hoisted(() => ({
  fetchMappedPageData: vi.fn(),
  fetchMappedPageDataset: vi.fn(),
  fetchMappedPageExport: vi.fn(),
  mappedAttachmentUrl: vi.fn(() => '/attachment'),
  fetchPersonAvatars: vi.fn(async () => ({})),
}))
const mocks = vi.hoisted(() => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

vi.mock('next/navigation', () => ({
  useRouter: () => navigation,
  useSearchParams: () => new URLSearchParams('dataset=binding-1'),
}))
vi.mock('@/lib/api/mapped-feishu', () => mappedApi)

type DropdownStubProps = {
  children?: ReactElement<{ onClick?: () => void }>
  dropdownRender?: () => ReactNode
}

type SelectStubProps = {
  value?: string
  onChange?: (value: string | undefined) => void
  options?: Array<{ label: ReactNode; value: string }>
  allowClear?: boolean
  placeholder?: string
}

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>()
  const { cloneElement, useState } = await import('react')
  return {
    ...actual,
    // 组件里的 message 来自 antd 的全局通知：它会创建独立 React root，并为每条
    // 提示挂一个约 3 秒的自动关闭定时器，用例结束后才触发渲染会在 happy-dom
    // 环境销毁后抛 "window is not defined"。这里只替换副作用边界。
    message: mocks.message,
    // 筛选/列设置的下拉浮层依赖 rc-trigger 的真实指针事件；换成"点击即内联
    // 展开"的桩，dropdownRender 内容与触发回调的契约保持不变
    Dropdown: ({ children, dropdownRender }: DropdownStubProps) => {
      const [open, setOpen] = useState(false)
      return (
        <>
          {cloneElement(children as ReactElement<{ onClick?: () => void }>, {
            onClick: () => setOpen((current) => !current),
          })}
          {open ? dropdownRender?.() : null}
        </>
      )
    },
    // 下拉选择的浮层同样依赖 rc-select 的指针事件；换成原生 <select>，
    // 组件用到的 value / onChange / options / allowClear 契约保持不变
    Select: (props: SelectStubProps) => (
      <select
        data-testid="antd-select"
        data-placeholder={props.placeholder}
        value={props.value ?? ''}
        onChange={(event) => props.onChange?.(event.target.value || undefined)}
      >
        {props.allowClear ? <option value="">（清除）</option> : null}
        {(props.options ?? []).map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    ),
  }
})

import { MappedDatasetPage } from './MappedDatasetPage'
import { UserFacingError } from '@/lib/user-error'

let root: Root | null = null
let container: HTMLElement

const pageData = {
  bindings: [{ id: 'binding-1', tab_label: '记录', is_default: true, table: { app_token: 'app-1' } }],
}

const twoBindings = {
  bindings: [
    { id: 'binding-1', tab_label: '记录', is_default: true, table: { app_token: 'app-1' } },
    { id: 'binding-2', tab_label: '领用记录', is_default: false, table: { app_token: 'app-1' } },
  ],
}

const dataset = {
  fields: [
    { field_id: 'applicant', field_name: '申请人' },
    { field_id: 'stamp_date', field_name: '用印日期', type: 5 },
    { field_id: 'status', field_name: '审批状态' },
  ],
  records: [
    {
      record_id: 'record-1',
      fields: { 申请人: '常晶晶', 用印日期: 1782230400000, 审批状态: '审批完成' },
    },
  ],
  pagination: { page: 1, page_size: 50, total: 1 },
}

type QueryParams = Record<string, unknown> | undefined

function renderPage(node: React.ReactNode) {
  container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
  act(() => {
    root!.render(node)
  })
}

/** 轮询到条件成立：React Query 的结果通知与浮层渲染都依赖真实定时器。 */
async function until(condition: () => boolean, message: string) {
  for (let i = 0; i < 80; i += 1) {
    if (condition()) return
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 25))
    })
  }
  throw new Error(message)
}

async function waitUntilLoaded(marker = '常晶晶') {
  await until(() => container.textContent?.includes(marker), `表格未渲染出标记文本: ${marker}`)
}

async function click(element: Element | undefined | null) {
  expect(element).toBeTruthy()
  await act(async () => {
    element!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  })
}

/** 去空白后按文案找按钮（antd 两字按钮会渲染成「删 除」）。 */
function buttonIn(rootNode: ParentNode, text: string): HTMLButtonElement | undefined {
  const needle = text.replace(/\s/g, '')
  return [...rootNode.querySelectorAll('button')].find((button) =>
    (button.textContent ?? '').replace(/\s/g, '').includes(needle),
  )
}

function lastQuery(): QueryParams {
  return mappedApi.fetchMappedPageDataset.mock.calls.at(-1)?.[3] as QueryParams
}

async function selectOption(select: HTMLSelectElement, value: string) {
  await act(async () => {
    select.value = value
    select.dispatchEvent(new Event('change', { bubbles: true }))
  })
}

async function typeInto(input: HTMLInputElement, value: string) {
  await act(async () => {
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')!.set!.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
}

beforeEach(() => {
  mappedApi.fetchMappedPageDataset.mockResolvedValue(dataset)
})

afterEach(async () => {
  await act(async () => root?.unmount())
  root = null
  // 卸载后让出一轮宏任务：React 调度器里排队的被动副作用必须在
  // happy-dom 环境销毁之前执行完
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
  document.body.innerHTML = ''
  vi.clearAllMocks()
})

describe('MappedDatasetPage 页签切换与默认排序', () => {
  it('切换页签：按新页签重查并同步 URL', async () => {
    renderPage(
      <MappedDatasetPage pageKey="warehouse.records" title="仓储记录" initialPageData={twoBindings} />,
    )
    await waitUntilLoaded()
    expect(mappedApi.fetchMappedPageDataset.mock.calls.every((call) => call[2] === 'binding-1')).toBe(true)

    const tab = [...container.querySelectorAll<HTMLElement>('.ant-tabs-tab')].find((node) =>
      node.textContent?.includes('领用记录'),
    )
    await click(tab)

    await until(
      () => mappedApi.fetchMappedPageDataset.mock.calls.some((call) => call[2] === 'binding-2'),
      '未按新页签重查数据',
    )
    expect(navigation.replace).toHaveBeenCalledWith('?dataset=binding-2')
  })

  it('默认排序：在指定页签把字段名映射成排序控件的选中值并下发', async () => {
    renderPage(
      <MappedDatasetPage
        pageKey="warehouse.records"
        title="仓储记录"
        initialPageData={pageData as never}
        defaultSort={{ tabName: '记录', fieldName: '审批状态', direction: 'asc' }}
      />,
    )
    await waitUntilLoaded()

    const sortSelect = container.querySelector<HTMLSelectElement>('select[data-placeholder="排序字段"]')
    // 排序控件显示为选中态：按字段名映射回字段 id
    expect(sortSelect?.value).toBe('status')
    // 下发给后端的是字段名（见 defaultSort 的约定），方向取配置值
    const sortedCalls = mappedApi.fetchMappedPageDataset.mock.calls
      .map((call) => call[3] as QueryParams)
      .filter((params) => params?.sort_field === '审批状态')
    expect(sortedCalls.length).toBeGreaterThan(0)
    expect(sortedCalls[0]).toMatchObject({ sort_field: '审批状态', sort_direction: 'asc' })
  })
})

describe('MappedDatasetPage 多条件筛选', () => {
  function fieldSelect(): HTMLSelectElement {
    const select = container.querySelector<HTMLSelectElement>('select[data-placeholder="筛选字段"]')
    expect(select).toBeTruthy()
    return select!
  }

  function operatorSelect(): HTMLSelectElement {
    const select = [...container.querySelectorAll<HTMLSelectElement>('select')].find((node) =>
      [...node.options].some((option) => option.value === 'contains'),
    )
    expect(select).toBeTruthy()
    return select!
  }

  function valueInput(): HTMLInputElement {
    const input = container.querySelector<HTMLInputElement>('input[placeholder="筛选值"]')
    expect(input).toBeTruthy()
    return input!
  }

  async function openFilterPanelAndAddCondition() {
    await click(buttonIn(container, '筛选'))
    await until(() => buttonIn(container, '添加条件') !== undefined, '筛选面板未展开')
    await click(buttonIn(container, '添加条件'))
    await until(
      () => container.querySelector('select[data-placeholder="筛选字段"]') !== null,
      '筛选条件行未渲染',
    )
  }

  it('条件进入查询参数并回第一页，按钮显示生效条件数', async () => {
    renderPage(
      <MappedDatasetPage
        pageKey="warehouse.records"
        title="仓储记录"
        initialPageData={pageData as never}
      />,
    )
    await waitUntilLoaded()
    await openFilterPanelAndAddCondition()

    // 字段与筛选值未填全的条件不生效
    expect(lastQuery()?.filters).toBeUndefined()

    await selectOption(fieldSelect(), 'applicant')
    await selectOption(operatorSelect(), 'eq')
    await typeInto(valueInput(), '常晶晶')

    await until(() => lastQuery()?.filters !== undefined, '筛选条件未进入查询')
    expect(lastQuery()).toMatchObject({
      filters: [{ field_id: 'applicant', operator: 'eq', value: '常晶晶' }],
      page: 1,
    })
    expect(buttonIn(container, '筛选')?.textContent).toContain('（1）')
  })

  it('删除条件后不再下发筛选', async () => {
    renderPage(
      <MappedDatasetPage
        pageKey="warehouse.records"
        title="仓储记录"
        initialPageData={pageData as never}
      />,
    )
    await waitUntilLoaded()
    await openFilterPanelAndAddCondition()
    await selectOption(fieldSelect(), 'status')
    await typeInto(valueInput(), '审批完成')
    await until(() => lastQuery()?.filters !== undefined, '筛选条件未进入查询')

    await click(buttonIn(container, '删除'))

    // 条件行移除、按钮不再显示生效条件数
    await until(
      () => container.querySelector('select[data-placeholder="筛选字段"]') === null,
      '删除后条件行仍在',
    )
    expect(buttonIn(container, '筛选')?.textContent).not.toContain('（')
    // 回到无筛选的查询：这一组条件曾缓存过，不会立即重发请求；
    // 手动刷新后的新请求不得再携带已删除的条件
    const callsBeforeRefresh = mappedApi.fetchMappedPageDataset.mock.calls.length
    await click(buttonIn(container, '刷新本地数据'))
    await until(
      () => mappedApi.fetchMappedPageDataset.mock.calls.length > callsBeforeRefresh,
      '刷新未重新请求数据',
    )
    expect(lastQuery()?.filters).toBeUndefined()
  })

  it('切换页签时清空已生效的筛选', async () => {
    renderPage(
      <MappedDatasetPage pageKey="warehouse.records" title="仓储记录" initialPageData={twoBindings} />,
    )
    await waitUntilLoaded()
    await openFilterPanelAndAddCondition()
    await selectOption(fieldSelect(), 'status')
    await typeInto(valueInput(), '审批完成')
    await until(() => lastQuery()?.filters !== undefined, '筛选条件未进入查询')

    const tab = [...container.querySelectorAll<HTMLElement>('.ant-tabs-tab')].find((node) =>
      node.textContent?.includes('领用记录'),
    )
    await click(tab)

    await until(
      () => mappedApi.fetchMappedPageDataset.mock.calls.some((call) => call[2] === 'binding-2'),
      '未按新页签重查数据',
    )
    expect(lastQuery()?.filters).toBeUndefined()
    expect(buttonIn(container, '筛选')?.textContent).not.toContain('（')
  })
})

describe('MappedDatasetPage 台账导出', () => {
  let downloads: Array<{ name: string | null; href: string | null }> = []
  let restoreObjectUrl: (() => void) | null = null

  beforeEach(() => {
    downloads = []
    const originalCreate = URL.createObjectURL
    const originalRevoke = URL.revokeObjectURL
    URL.createObjectURL = vi.fn(() => 'blob:ledger-export')
    URL.revokeObjectURL = vi.fn()
    restoreObjectUrl = () => {
      URL.createObjectURL = originalCreate
      URL.revokeObjectURL = originalRevoke
    }
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      downloads.push({ name: this.getAttribute('download'), href: this.getAttribute('href') })
    })
  })

  afterEach(() => {
    restoreObjectUrl?.()
    restoreObjectUrl = null
    vi.restoreAllMocks()
  })

  function renderExportable() {
    renderPage(
      <MappedDatasetPage
        pageKey="warehouse.records"
        title="仓储记录"
        initialPageData={pageData as never}
        enableExport
      />,
    )
  }

  it('导出 Excel：按当前列与排序请求文件并触发浏览器下载', async () => {
    const blob = new Blob(['sheet'], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    mappedApi.fetchMappedPageExport.mockResolvedValue(blob)
    renderExportable()
    await waitUntilLoaded()

    await click(buttonIn(container, '导出 Excel'))

    await until(() => downloads.length > 0, '未触发浏览器下载')
    expect(mappedApi.fetchMappedPageExport).toHaveBeenCalledTimes(1)
    expect(mappedApi.fetchMappedPageExport).toHaveBeenCalledWith(
      'warehouse',
      'warehouse.records',
      'binding-1',
      {
        format: 'xlsx',
        columns: ['stamp_date', 'applicant', 'status'],
        filters: [],
        sort_field: 'stamp_date',
        sort_direction: 'desc',
      },
    )
    expect(URL.createObjectURL).toHaveBeenCalledWith(blob)
    expect(downloads[0]?.href).toBe('blob:ledger-export')
    expect(downloads[0]?.name).toMatch(/^仓储记录-\d{4}-\d{2}-\d{2}\.xlsx$/)
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:ledger-export')
    expect(mocks.message.error).not.toHaveBeenCalled()
  })

  it('导出 PDF：使用 PDF 格式与同名下载', async () => {
    mappedApi.fetchMappedPageExport.mockResolvedValue(new Blob(['pdf'], { type: 'application/pdf' }))
    renderExportable()
    await waitUntilLoaded()

    await click(buttonIn(container, '导出 PDF'))

    await until(() => downloads.length > 0, '未触发浏览器下载')
    expect(mappedApi.fetchMappedPageExport.mock.calls[0][3]).toMatchObject({ format: 'pdf' })
    expect(downloads[0]?.name).toMatch(/^仓储记录-\d{4}-\d{2}-\d{2}\.pdf$/)
  })

  it('导出失败：提示可读错误并复位按钮加载态', async () => {
    mappedApi.fetchMappedPageExport.mockRejectedValue(new UserFacingError('导出服务暂不可用'))
    renderExportable()
    await waitUntilLoaded()

    await click(buttonIn(container, '导出 Excel'))

    await until(() => mocks.message.error.mock.calls.length > 0, '导出失败未提示')
    expect(mocks.message.error).toHaveBeenCalledWith('导出服务暂不可用')
    expect(downloads).toHaveLength(0)
    await until(
      () => buttonIn(container, '导出 Excel')?.className.includes('ant-btn-loading') === false,
      '导出失败后按钮仍在加载中',
    )
  })

  it('未开启导出的页面不渲染导出入口', async () => {
    renderPage(
      <MappedDatasetPage
        pageKey="warehouse.records"
        title="仓储记录"
        initialPageData={pageData as never}
      />,
    )
    await waitUntilLoaded()
    expect(buttonIn(container, '导出')).toBeUndefined()
    expect(mappedApi.fetchMappedPageExport).not.toHaveBeenCalled()
  })
})
