/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  noticeApi: {
    fetchNoticeList: vi.fn(),
    fetchNoticeDetail: vi.fn(),
    fetchNoticeContent: vi.fn(),
    noticeFileUrl: vi.fn(
      (id: string) => `/api/v1/administration/notices/${id}/file`,
    ),
    updateNotice: vi.fn(),
    deleteNotice: vi.fn(),
  },
  auth: { hasPagePermission: vi.fn(() => false) },
  routerReplace: vi.fn(),
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  // 留住上传弹窗的回调供用例直接触发（弹窗本体由 NoticeImportModal.test.tsx 覆盖）
  importModalProps: {} as Record<string, unknown>,
}))

type SelectStubProps = {
  value?: string
  onChange?: (value: string | undefined) => void
  options?: Array<{ label: string; value: string }>
  allowClear?: boolean
}

vi.mock('next/navigation', () => ({
  usePathname: () => '/admin/notice',
  useRouter: () => ({ replace: mocks.routerReplace }),
  useSearchParams: () => new URLSearchParams(),
}))

vi.mock('@/lib/api/notice', () => mocks.noticeApi)

vi.mock('@/stores/auth', () => ({
  useAuthStore: (selector: (state: typeof mocks.auth) => unknown) =>
    selector(mocks.auth),
}))

vi.mock('./NoticeImportModal', () => ({
  default: (props: Record<string, unknown>) => {
    mocks.importModalProps = props
    return (
      <div data-testid="notice-import-modal" data-open={String(props.open)} />
    )
  },
}))

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>()
  return {
    ...actual,
    // 组件里的 message 来自 antd 的全局通知：它会创建独立 React root，并为每条
    // 提示挂一个约 3 秒的自动关闭定时器。用例若在该定时器到期前结束，定时器会在
    // happy-dom 环境销毁之后触发渲染，抛 "ReferenceError: window is not defined"，
    // 让整次测试以未处理错误失败（用例本身全部通过）。这里只替换副作用边界，
    // 保留 antd 其余组件与主题的真实实现。
    message: mocks.message,
    App: { ...actual.App, useApp: () => ({ message: mocks.message }) },
    // 类别筛选的浮层依赖 rc-select 的真实指针事件；换成原生 <select>，
    // 组件用到的 value / onChange / options / allowClear 契约保持不变
    Select: (props: SelectStubProps) => (
      <select
        data-testid="category-select"
        value={props.value ?? ''}
        onChange={(event) => props.onChange?.(event.target.value || undefined)}
      >
        {props.allowClear ? <option value="">全部类别</option> : null}
        {(props.options ?? []).map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    ),
  }
})

import NoticeWorkspace from './NoticeWorkspace'
import type { NoticeItem, NoticeListResponse } from '@/types/administration'

const NOTICE_ID = '11111111-1111-4111-8111-111111111111'
const NOTICE_TITLE = '年度安全培训通知'

let root: Root | null = null

function notice(overrides: Partial<NoticeItem> = {}): NoticeItem {
  return {
    id: NOTICE_ID,
    notice_no: '2026-001',
    title: '年度安全培训通知',
    publisher: '安全环保部',
    published_at: '2026-03-05',
    category: '安全公告',
    remark: null,
    source_file_name: '培训公告.docx',
    source_size_bytes: 1024,
    created_at: '2026-03-05T02:00:00Z',
    updated_at: '2026-03-05T02:00:00Z',
    ...overrides,
  }
}

function listResponse(items: NoticeItem[]): NoticeListResponse {
  return {
    items,
    total: items.length,
    page: 1,
    page_size: 20,
    categories: ['安全公告'],
  }
}

function render(node: React.ReactNode) {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  root = createRoot(container)
  act(() => {
    root!.render(<QueryClientProvider client={client}>{node}</QueryClientProvider>)
  })
  return container
}

async function flush(rounds = 3) {
  for (let i = 0; i < rounds; i += 1) {
    await act(async () => {
      await Promise.resolve()
    })
  }
}

/** 轮询到表格行渲染完成（React Query 异步解析 + antd 渲染）。 */
async function waitForRows(container: HTMLElement, marker: string) {
  for (let i = 0; i < 60; i += 1) {
    if (container.textContent?.includes(marker)) return
    await flush(2)
    // 组件内置 QueryClient 失败重试带真实退避，需让出事件循环时间
    await new Promise((resolve) => setTimeout(resolve, 50))
  }
  throw new Error(`表格未渲染出标记文本: ${marker}`)
}

function bodyText(): string {
  document.querySelectorAll('svg').forEach((node) => node.remove())
  return document.body.textContent || ''
}

/** 去空白后按文案找按钮（antd 两字按钮会渲染成「保 存」）。 */
function buttonIn(root: ParentNode, text: string): HTMLButtonElement | undefined {
  const needle = text.replace(/\s/g, '')
  return [...root.querySelectorAll('button')].find((button) =>
    (button.textContent ?? '').replace(/\s/g, '').includes(needle),
  )
}

/** 轮询到条件成立：Modal/Popconfirm 挂在 portal，渲染依赖动画帧与定时器。 */
async function until(condition: () => boolean, message: string) {
  for (let i = 0; i < 80; i += 1) {
    if (condition()) return
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 25))
    })
  }
  throw new Error(message)
}

async function click(element: Element | undefined | null) {
  expect(element).toBeTruthy()
  await act(async () => {
    element!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  })
}

async function lastReplacedQuery(): Promise<URLSearchParams> {
  const target = String(mocks.routerReplace.mock.calls.at(-1)?.[0] ?? '')
  return new URLSearchParams(target.split('?')[1] ?? '')
}

beforeEach(() => {
  mocks.noticeApi.fetchNoticeList.mockResolvedValue(listResponse([notice()]))
  mocks.noticeApi.fetchNoticeDetail.mockResolvedValue(notice())
  mocks.noticeApi.fetchNoticeContent.mockResolvedValue({
    id: NOTICE_ID,
    notice_no: '2026-001',
    title: NOTICE_TITLE,
    content: '机密公告正文内容',
  })
  mocks.noticeApi.updateNotice.mockResolvedValue(notice())
  mocks.noticeApi.deleteNotice.mockResolvedValue(undefined)
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

describe('NoticeWorkspace', () => {
  it('renders ledger metadata without ever exposing notice content', async () => {
    const container = render(<NoticeWorkspace />)
    await waitForRows(container, '年度安全培训通知')
    const text = bodyText()
    expect(text).toContain('2026-001')
    expect(text).toContain('安全环保部')
    expect(text).not.toContain('机密公告正文内容')
  })

  it('hides operate-only actions for query-only users', async () => {
    mocks.auth.hasPagePermission.mockReturnValue(false)
    const container = render(<NoticeWorkspace />)
    await waitForRows(container, '年度安全培训通知')
    // 上传入口以禁用态呈现（权限不足可见不可用）
    const uploadButton = [...container.querySelectorAll('button')].find((button) =>
      button.textContent?.includes('上传公告'),
    )
    expect(uploadButton?.disabled).toBe(true)
    const text = bodyText()
    expect(text).not.toContain('删除')
    expect(text).not.toContain('编辑')
    expect(text).not.toContain('原文')
  })

  it('shows operate actions and opens the import modal for operators', async () => {
    mocks.auth.hasPagePermission.mockReturnValue(true)
    const container = render(<NoticeWorkspace />)
    await waitForRows(container, '年度安全培训通知')
    expect(container.textContent).toContain('上传公告')

    const openButton = [...container.querySelectorAll('button')].find((button) =>
      button.textContent?.includes('上传公告'),
    )
    expect(openButton).toBeTruthy()
    await act(async () => {
      openButton!.click()
      await Promise.resolve()
    })
    const modal = document.querySelector('[data-testid="notice-import-modal"]')
    expect(modal?.getAttribute('data-open')).toBe('true')
  })

  it('loads notice content only through the operate-only endpoint', async () => {
    mocks.auth.hasPagePermission.mockReturnValue(true)
    const container = render(<NoticeWorkspace />)
    await waitForRows(container, '年度安全培训通知')

    const contentButton = [...container.querySelectorAll('button')].find((button) =>
      button.textContent?.includes('内容'),
    )
    await act(async () => {
      contentButton!.click()
      await Promise.resolve()
    })
    await flush(4)
    expect(mocks.noticeApi.fetchNoticeContent).toHaveBeenCalledWith(
      '11111111-1111-4111-8111-111111111111',
    )
    expect(bodyText()).toContain('机密公告正文内容')
  })

  it('deletes with confirmation and refreshes the list', async () => {
    mocks.auth.hasPagePermission.mockReturnValue(true)
    const container = render(<NoticeWorkspace />)
    await waitForRows(container, '年度安全培训通知')

    const deleteButton = [...container.querySelectorAll('button')].find((button) =>
      button.textContent?.includes('删除'),
    )
    expect(deleteButton).toBeTruthy()
    await act(async () => {
      deleteButton!.click()
      await Promise.resolve()
    })
    await flush(2)
    const confirmButton = [...document.querySelectorAll('button')].find(
      (button) => button.textContent === '删 除',
    )
    await act(async () => {
      confirmButton!.click()
      await Promise.resolve()
    })
    await flush(3)
    expect(mocks.noticeApi.deleteNotice).toHaveBeenCalledWith(
      '11111111-1111-4111-8111-111111111111',
    )
  })

  it('surfaces list failures explicitly', async () => {
    mocks.noticeApi.fetchNoticeList.mockRejectedValue(new Error('网络故障'))
    const container = render(<NoticeWorkspace />)
    await waitForRows(container, '网络故障')
    expect(container.textContent).toContain('网络故障')
  })

  it('submits keyword search into the URL query and resets page', async () => {
    mocks.auth.hasPagePermission.mockReturnValue(true)
    const container = render(<NoticeWorkspace />)
    await waitForRows(container, '年度安全培训通知')

    const searchInput = container.querySelector<HTMLInputElement>(
      '.ant-input-search input',
    )!
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!
        .set!.call(searchInput, '培训')
      searchInput.dispatchEvent(new Event('input', { bubbles: true }))
      searchInput.dispatchEvent(new Event('change', { bubbles: true }))
    })
    const candidates = [...container.querySelectorAll('button')]
    // antd v6：搜索按钮带 ant-input-search 与 ant-btn-compact-last-item 类
    const searchButton = candidates.find((button) =>
      button.className.includes('ant-input-search'),
    )
    await act(async () => {
      searchButton!.click()
      await Promise.resolve()
    })

    expect(mocks.routerReplace).toHaveBeenCalledTimes(1)
    const target = String(mocks.routerReplace.mock.calls[0][0])
    const query = new URLSearchParams(target.split('?')[1] ?? '')
    expect(query.get('keyword')).toBe('培训')
    expect(query.has('page')).toBe(false)
  })
})

/**
 * 未关闭的 Modal 是否含该标题。happy-dom 不触发 transitionend，Modal 关闭后节点
 * 不会隐藏，而是停在关闭动画类上——以动画类区分打开/关闭态。
 */
function modalShown(title: string): boolean {
  return [...document.body.querySelectorAll<HTMLElement>('.ant-modal')].some(
    (modal) =>
      modal.textContent?.includes(title) && !modal.classList.contains('ant-zoom-leave'),
  )
}

describe('NoticeWorkspace 编辑弹窗全链与错误分支', () => {
  function renderOperate() {
    mocks.auth.hasPagePermission.mockReturnValue(true)
    return render(<NoticeWorkspace />)
  }

  function formValues(): string[] {
    return [...document.body.querySelectorAll<HTMLInputElement>('input')].map(
      (input) => input.value,
    )
  }

  async function openEdit(container: HTMLElement) {
    await waitForRows(container, NOTICE_TITLE)
    await click(buttonIn(container, '编辑'))
    // 元数据与正文两个端点都返回后才预填完成：以标题输入框的值为就绪信号
    await until(
      () => formValues().includes(NOTICE_TITLE),
      '编辑表单未按服务端数据预填',
    )
  }

  it('编辑弹窗打开：经 operate 端点取回元数据与正文预填', async () => {
    const container = renderOperate()
    await openEdit(container)
    expect(mocks.noticeApi.fetchNoticeDetail).toHaveBeenCalledWith(NOTICE_ID)
    expect(mocks.noticeApi.fetchNoticeContent).toHaveBeenCalledWith(NOTICE_ID)
    expect(formValues()).toEqual(
      expect.arrayContaining(['2026-001', NOTICE_TITLE, '安全环保部', '2026-03-05', '安全公告']),
    )
    expect(document.body.querySelector('textarea')?.value).toBe('机密公告正文内容')
  })

  it('详情/内容端点失败：提示错误但不阻塞弹窗打开', async () => {
    mocks.noticeApi.fetchNoticeDetail.mockRejectedValue(new Error('详情失败'))
    mocks.noticeApi.fetchNoticeContent.mockRejectedValue(new Error('内容失败'))
    const container = renderOperate()
    await waitForRows(container, NOTICE_TITLE)
    await click(buttonIn(container, '编辑'))
    await until(() => document.body.textContent?.includes('编辑公告'), '编辑弹窗未打开')

    await until(() => mocks.message.error.mock.calls.length > 0, '端点失败未提示')
    expect(mocks.message.error).toHaveBeenCalledWith('读取公告详情失败，请关闭后重试')
    // 预填失败时表单仍打开，可手工填写
    expect(formValues()).toContain('')
  })

  it('保存：把表单值提交到更新端点，成功后提示并刷新台账', async () => {
    const container = renderOperate()
    await openEdit(container)
    const listCalls = mocks.noticeApi.fetchNoticeList.mock.calls.length

    await click(buttonIn(document.body, '保存'))

    await until(() => mocks.message.success.mock.calls.length > 0, '保存成功未提示')
    expect(mocks.noticeApi.updateNotice).toHaveBeenCalledWith(
      NOTICE_ID,
      expect.objectContaining({
        notice_no: '2026-001',
        title: NOTICE_TITLE,
        publisher: '安全环保部',
        published_at: '2026-03-05',
        category: '安全公告',
        content: '机密公告正文内容',
      }),
    )
    expect(mocks.message.success).toHaveBeenCalledWith('公告已更新')
    await until(
      () => mocks.noticeApi.fetchNoticeList.mock.calls.length > listCalls,
      '保存成功后未刷新台账',
    )
  })

  it('保存失败：提示后端错误且不刷新台账', async () => {
    mocks.noticeApi.updateNotice.mockRejectedValue(new Error('公告编号已存在'))
    const container = renderOperate()
    await openEdit(container)
    const listCalls = mocks.noticeApi.fetchNoticeList.mock.calls.length

    await click(buttonIn(document.body, '保存'))

    await until(() => mocks.message.error.mock.calls.length > 0, '保存失败未提示')
    expect(mocks.message.error).toHaveBeenCalledWith('公告编号已存在')
    expect(mocks.message.success).not.toHaveBeenCalled()
    expect(mocks.noticeApi.fetchNoticeList).toHaveBeenCalledTimes(listCalls)
  })

  it('关闭编辑弹窗：不提交任何修改', async () => {
    const container = renderOperate()
    await openEdit(container)

    await click(document.body.querySelector('.ant-modal-close'))

    await until(() => !modalShown('编辑公告'), '编辑弹窗未关闭')
    expect(mocks.noticeApi.updateNotice).not.toHaveBeenCalled()
  })
})

describe('NoticeWorkspace 原文、失败分支与列表操作', () => {
  const NOTICE_ID_2 = '22222222-2222-4222-8222-222222222222'

  function renderOperate() {
    mocks.auth.hasPagePermission.mockReturnValue(true)
    return render(<NoticeWorkspace />)
  }

  it('原文：有存档时新窗口打开文件，无存档时提示且不打开', async () => {
    const open = vi.spyOn(window, 'open').mockImplementation(() => null)
    try {
      mocks.noticeApi.fetchNoticeList.mockResolvedValue(
        listResponse([
          notice(),
          notice({ id: NOTICE_ID_2, notice_no: '2026-002', source_file_name: undefined }),
        ]),
      )
      const container = renderOperate()
      await waitForRows(container, '2026-002')

      const fileButtons = [...container.querySelectorAll('button')].filter((button) =>
        button.textContent?.includes('原文'),
      )
      expect(fileButtons).toHaveLength(2)
      await click(fileButtons[0])
      expect(open).toHaveBeenCalledWith(
        `/api/v1/administration/notices/${NOTICE_ID}/file`,
        '_blank',
      )

      await click(fileButtons[1])
      expect(open).toHaveBeenCalledTimes(1)
      expect(mocks.message.warning).toHaveBeenCalledWith('该公告没有原文存档')
    } finally {
      open.mockRestore()
    }
  })

  it('内容读取失败：提示错误并关闭内容弹窗', async () => {
    mocks.noticeApi.fetchNoticeContent.mockRejectedValue(new Error('无权查看'))
    const container = renderOperate()
    await waitForRows(container, NOTICE_TITLE)

    await click(buttonIn(container, '内容'))

    await until(() => mocks.message.error.mock.calls.length > 0, '读取失败未提示')
    expect(mocks.message.error).toHaveBeenCalledWith('无权查看')
    // 失败后不留下「正在读取」的空壳弹窗
    await until(() => !modalShown('公告内容'), '读取失败后内容弹窗未关闭')
  })

  it('内容读取抛出非 Error 值：回退通用提示', async () => {
    mocks.noticeApi.fetchNoticeContent.mockRejectedValue('boom')
    const container = renderOperate()
    await waitForRows(container, NOTICE_TITLE)

    await click(buttonIn(container, '内容'))

    await until(() => mocks.message.error.mock.calls.length > 0, '读取失败未提示')
    expect(mocks.message.error).toHaveBeenCalledWith('读取公告内容失败')
  })

  it('点击内容弹窗的关闭按钮：收起弹窗', async () => {
    const container = renderOperate()
    await waitForRows(container, NOTICE_TITLE)
    await click(buttonIn(container, '内容'))
    await until(() => bodyText().includes('机密公告正文内容'), '公告内容未展示')

    await click(document.body.querySelector('.ant-modal-close'))

    await until(() => !modalShown('公告内容'), '内容弹窗未关闭')
  })

  it('删除失败：提示错误且不报告成功', async () => {
    mocks.noticeApi.deleteNotice.mockRejectedValue(new Error('删除失败'))
    const container = renderOperate()
    await waitForRows(container, NOTICE_TITLE)
    await click(buttonIn(container, '删除'))

    // 确认按钮在 Popconfirm 的 portal 里（不在表格容器内）
    const confirmButton = () =>
      [...document.body.querySelectorAll('button')].find(
        (button) =>
          !container.contains(button) &&
          (button.textContent ?? '').replace(/\s/g, '') === '删除',
      )
    await until(() => confirmButton() !== undefined, '删除确认框未出现')
    await click(confirmButton())

    await until(() => mocks.message.error.mock.calls.length > 0, '删除失败未提示')
    expect(mocks.message.error).toHaveBeenCalledWith('删除失败')
    expect(mocks.message.success).not.toHaveBeenCalled()
  })

  it('刷新：重新请求台账列表', async () => {
    const container = renderOperate()
    await waitForRows(container, NOTICE_TITLE)
    const calls = mocks.noticeApi.fetchNoticeList.mock.calls.length

    await click(buttonIn(container, '刷新'))

    await until(
      () => mocks.noticeApi.fetchNoticeList.mock.calls.length > calls,
      '刷新未重新请求列表',
    )
    expect(mocks.routerReplace).not.toHaveBeenCalled()
  })

  it('类别筛选：提交到 URL 并回第一页', async () => {
    const container = renderOperate()
    await waitForRows(container, NOTICE_TITLE)

    const select = container.querySelector<HTMLSelectElement>(
      '[data-testid="category-select"]',
    )!
    expect([...select.options].map((option) => option.value)).toEqual(['', '安全公告'])
    await act(async () => {
      select.value = '安全公告'
      select.dispatchEvent(new Event('change', { bubbles: true }))
    })

    const query = await lastReplacedQuery()
    expect(query.get('category')).toBe('安全公告')
    expect(query.has('page')).toBe(false)
  })

  it('清空类别：从 URL 删除筛选条件', async () => {
    const container = renderOperate()
    await waitForRows(container, NOTICE_TITLE)

    const select = container.querySelector<HTMLSelectElement>(
      '[data-testid="category-select"]',
    )!
    await act(async () => {
      select.value = ''
      select.dispatchEvent(new Event('change', { bubbles: true }))
    })

    expect(mocks.routerReplace).toHaveBeenCalledTimes(1)
    expect((await lastReplacedQuery()).has('category')).toBe(false)
  })

  it('翻页：页码与页大小写入 URL', async () => {
    mocks.noticeApi.fetchNoticeList.mockResolvedValue({
      ...listResponse([notice()]),
      total: 41,
    })
    const container = renderOperate()
    await waitForRows(container, NOTICE_TITLE)

    await click(container.querySelector('.ant-pagination-item-2'))

    const query = await lastReplacedQuery()
    expect(query.get('page')).toBe('2')
    expect(query.get('page_size')).toBe('20')
  })

  it('上传弹窗关闭：收起弹窗', async () => {
    const container = renderOperate()
    await waitForRows(container, NOTICE_TITLE)
    await click(buttonIn(container, '上传公告'))
    await until(() => mocks.importModalProps.open === true, '上传弹窗未打开')

    await act(async () => {
      ;(mocks.importModalProps.onClose as () => void)()
    })

    await until(() => mocks.importModalProps.open === false, '上传弹窗未关闭')
  })
})
