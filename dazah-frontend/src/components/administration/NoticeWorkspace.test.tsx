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
}))

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
  default: (props: Record<string, unknown>) => (
    <div data-testid="notice-import-modal" data-open={String(props.open)} />
  ),
}))

import { App as AntdApp } from 'antd'

import NoticeWorkspace from './NoticeWorkspace'
import type { NoticeItem, NoticeListResponse } from '@/types/administration'

let root: Root | null = null

function notice(overrides: Partial<NoticeItem> = {}): NoticeItem {
  return {
    id: '11111111-1111-4111-8111-111111111111',
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
    root!.render(
      <AntdApp>
        <QueryClientProvider client={client}>{node}</QueryClientProvider>
      </AntdApp>,
    )
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

beforeEach(() => {
  mocks.noticeApi.fetchNoticeList.mockResolvedValue(listResponse([notice()]))
  mocks.noticeApi.fetchNoticeContent.mockResolvedValue({
    id: '11111111-1111-4111-8111-111111111111',
    notice_no: '2026-001',
    title: '年度安全培训通知',
    content: '机密公告正文内容',
  })
  mocks.noticeApi.deleteNotice.mockResolvedValue(undefined)
})

afterEach(() => {
  act(() => root?.unmount())
  root = null
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
