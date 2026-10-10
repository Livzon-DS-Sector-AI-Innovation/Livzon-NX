/* @vitest-environment happy-dom */

import { act, createElement, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => {
  const message = { success: vi.fn(), error: vi.fn(), warning: vi.fn() }
  const modal = { confirm: vi.fn() }
  const form = {
    resetFields: vi.fn(),
    setFieldsValue: vi.fn(),
    validateFields: vi.fn(async () => ({ title: '新建法规' })),
  }
  return {
    message,
    modal,
    form,
    uploadKnowledgeAttachments: vi.fn(),
    deleteKnowledgeAttachment: vi.fn(),
    getKnowledgeArticles: vi.fn(),
    getKnowledgeArticle: vi.fn(),
    createKnowledgeArticle: vi.fn(),
    updateKnowledgeArticle: vi.fn(),
    deleteKnowledgeArticle: vi.fn(),
    syncSafetyKnowledge: vi.fn(),
    getRadarRuns: vi.fn(),
    getRadarRunDetail: vi.fn(),
    runRadarScan: vi.fn(),
    store: {
      articles: [] as Record<string, unknown>[],
      articleTotal: 0,
      articleQueryParams: { page: 1, page_size: 10 },
      setArticles: vi.fn(),
      setArticleTotal: vi.fn(),
      setArticleQueryParams: vi.fn(),
      addArticle: vi.fn(),
      updateArticle: vi.fn(),
      removeArticle: vi.fn(),
    },
  }
})

vi.mock('@/actions/safety', () => ({
  uploadKnowledgeAttachments: mocks.uploadKnowledgeAttachments,
  deleteKnowledgeAttachment: mocks.deleteKnowledgeAttachment,
  getKnowledgeArticles: mocks.getKnowledgeArticles,
  getKnowledgeArticle: mocks.getKnowledgeArticle,
  createKnowledgeArticle: mocks.createKnowledgeArticle,
  updateKnowledgeArticle: mocks.updateKnowledgeArticle,
  deleteKnowledgeArticle: mocks.deleteKnowledgeArticle,
  syncSafetyKnowledge: mocks.syncSafetyKnowledge,
  getRadarRuns: mocks.getRadarRuns,
  getRadarRunDetail: mocks.getRadarRunDetail,
  runRadarScan: mocks.runRadarScan,
}))

vi.mock('@/components/shared/PlatformNotice', async () => {
  const { createElement } = await import('react')
  return {
    default: ({ title, action, showRulesLink }: Record<string, unknown>) =>
      createElement(
        'div',
        { 'data-notice': 'true', 'data-show-rules-link': String(showRulesLink) },
        title as ReactNode,
        action as ReactNode
      ),
  }
})

vi.mock('@/stores/safety', () => ({ useSafetyStore: () => mocks.store }))

vi.mock('@ant-design/icons', () => {
  const Icon = () => null
  return {
    PaperClipOutlined: Icon,
    UploadOutlined: Icon,
    PlusOutlined: Icon,
    SearchOutlined: Icon,
    EditOutlined: Icon,
    DeleteOutlined: Icon,
    EyeOutlined: Icon,
    CloudDownloadOutlined: Icon,
    FilePdfOutlined: Icon,
    LinkOutlined: Icon,
  }
})

vi.mock('antd', async () => {
  const { createElement } = await import('react')

  type AnyProps = Record<string, unknown> & { children?: ReactNode }

  const Box = ({ children, title, extra }: AnyProps) =>
    createElement('div', null, title as ReactNode, extra as ReactNode, children as ReactNode)
  const Text = ({ children }: AnyProps) => createElement('span', null, children as ReactNode)
  const Button = ({ children, onClick, disabled, href }: AnyProps) =>
    href
      ? createElement('a', { href: href as string }, children as ReactNode)
      : createElement(
          'button',
          { type: 'button', disabled: Boolean(disabled), onClick: onClick as never },
          children as ReactNode
        )
  const Input = Object.assign(
    ({ value, onChange, onPressEnter, placeholder }: AnyProps) =>
      createElement('input', {
        value: (value as string) ?? '',
        placeholder: placeholder as string,
        onChange: (event: { target: { value: string } }) =>
          (onChange as ((e: unknown) => void) | undefined)?.(event),
        onKeyDown: (event: { key: string }) => {
          if (event.key === 'Enter') (onPressEnter as (() => void) | undefined)?.()
        },
      }),
    {
      TextArea: ({ value, onChange, placeholder }: AnyProps) =>
        createElement('textarea', {
          value: (value as string) ?? '',
          placeholder: placeholder as string,
          onChange: (event: { target: { value: string } }) =>
            (onChange as ((e: unknown) => void) | undefined)?.(event),
        }),
    }
  )
  const Select = ({ value, onChange, options }: AnyProps) =>
    createElement(
      'select',
      {
        value: (value as string) ?? '',
        onChange: (event: { target: { value: string } }) =>
          (onChange as ((v: string) => void) | undefined)?.(event.target.value),
      },
      createElement('option', { key: 'empty', value: '' }, ''),
      ((options as { value: string; label: string }[]) ?? []).map((option) =>
        createElement('option', { key: option.value, value: option.value }, option.label)
      )
    )
  const Table = ({ columns, dataSource, pagination }: AnyProps) => {
    const cols = (columns as {
      key: string
      dataIndex?: string
      title: string
      render?: (value: unknown, record: Record<string, unknown>) => ReactNode
    }[]) ?? []
    const rows = (dataSource as Record<string, unknown>[]) ?? []
    const pager = pagination as { onChange?: (page: number, size: number) => void } | undefined
    return createElement(
      'div',
      null,
      createElement(
        'table',
        null,
        createElement(
          'thead',
          null,
          createElement(
            'tr',
            null,
            cols.map((column) => createElement('th', { key: column.key }, column.title))
          )
        ),
        createElement(
          'tbody',
          null,
          rows.map((row, index) =>
            createElement(
              'tr',
              { key: String(row.id ?? index) },
              cols.map((column) =>
                createElement(
                  'td',
                  { key: column.key },
                  column.render
                    ? column.render(row[column.dataIndex as string], row)
                    : String(row[column.dataIndex as string] ?? '')
                )
              )
            )
          )
        )
      ),
      pager?.onChange
        ? createElement(
            'button',
            { type: 'button', 'data-pagination': 'next', onClick: () => pager.onChange?.(2, 10) },
            '翻页'
          )
        : null
    )
  }
  const Modal = ({ open, children, title, okText, cancelText, onOk, onCancel }: AnyProps) => {
    if (open === false) return null
    return createElement(
      'div',
      null,
      title ? createElement('div', { 'data-modal-title': 'true' }, title as ReactNode) : null,
      children as ReactNode,
      okText
        ? createElement('button', { type: 'button', onClick: onOk as never }, okText as ReactNode)
        : null,
      cancelText
        ? createElement('button', { type: 'button', onClick: onCancel as never }, cancelText as ReactNode)
        : null
    )
  }
  const Upload = ({ children, beforeUpload }: AnyProps) =>
    createElement(
      'div',
      null,
      children as ReactNode,
      createElement(
        'button',
        {
          type: 'button',
          'data-upload': 'true',
          onClick: () =>
            (beforeUpload as ((file: File) => boolean) | undefined)?.(
              new File(['abc'], 'sop.pdf', { type: 'application/pdf' })
            ),
        },
        'upload'
      )
    )
  const Form = Object.assign(({ children }: AnyProps) => createElement('form', null, children as ReactNode), {
    Item: ({ children, label }: AnyProps) =>
      createElement('div', { 'data-label': String(label ?? '') }, children as ReactNode),
    useForm: () => [mocks.form],
  })

  return {
    App: { useApp: () => ({ message: mocks.message, modal: mocks.modal }) },
    Button,
    Card: Box,
    Col: Box,
    DatePicker: ({ placeholder }: AnyProps) =>
      createElement('input', { placeholder: placeholder as string }),
    Descriptions: Object.assign(Box, {
      Item: ({ children }: AnyProps) => createElement('div', null, children as ReactNode),
    }),
    Form,
    Input,
    Modal,
    Row: Box,
    Select,
    Space: Object.assign(Box, { Compact: Box }),
    Spin: () => createElement('span', null, 'spin'),
    Table,
    Tag: Text,
    Typography: { Text, Title: Text },
    Upload,
  }
})

import KnowledgeBasePage from './page'

type Rendered = { root: Root; container: HTMLDivElement }

const article = (overrides: Record<string, unknown> = {}) => ({
  id: 'doc-1',
  article_no: '001',
  title: '危险化学品安全管理条例',
  regulation_category: '安全类',
  source: '国务院',
  regulation_status: '现行有效',
  promulgation_date: '2026-01-02T00:00:00.000Z',
  implement_date: null,
  regulation_link: 'https://example.com/law',
  summary: '要点',
  notes: '备注',
  feishu_record_id: 'rec-1',
  feishu_attachments: [{ file_token: 'tok-f', name: '法规.pdf' }],
  local_attachments: [{ token: 'tok-l', name: '本地.pdf', size: 2048 }],
  created_at: '2026-01-01T00:00:00.000Z',
  updated_at: '2026-01-02T00:00:00.000Z',
  ...overrides,
})

function renderPage(): Rendered {
  const container = document.createElement('div')
  document.body.append(container)
  const root = createRoot(container)
  act(() => {
    root.render(createElement(KnowledgeBasePage))
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

function uploadButton(container: HTMLElement): HTMLButtonElement[] {
  return Array.from(container.querySelectorAll('button[data-upload="true"]')) as HTMLButtonElement[]
}

let rendered: Rendered | undefined
let openSpy: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  mocks.getKnowledgeArticles.mockResolvedValue({ code: 200, data: [article()], meta: { total: 1 } })
  mocks.getRadarRuns.mockResolvedValue({ code: 200, data: [] })
  mocks.getRadarRunDetail.mockResolvedValue({ code: 200, data: { id: 'run-1', items: [] } })
  mocks.runRadarScan.mockResolvedValue({
    code: 200,
    data: { status: 'success', new_count: 0, revised_count: 0 },
  })
  mocks.store.articles = [article()]
  mocks.store.articleTotal = 1
  openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
})

afterEach(() => {
  if (rendered) {
    act(() => rendered?.root.unmount())
    rendered.container.remove()
    rendered = undefined
  }
  openSpy.mockRestore()
  vi.clearAllMocks()
})

describe('safety knowledge base page', () => {
  it('loads the list on mount and formats status, dates and attachments', async () => {
    rendered = renderPage()
    await settle()

    expect(mocks.getKnowledgeArticles).toHaveBeenCalledWith({
      page: 1,
      page_size: 10,
      regulation_status: undefined,
      keyword: undefined,
    })
    const markup = rendered.container.innerHTML
    expect(markup).toContain('危险化学品安全管理条例')
    expect(markup).toContain('现行有效')
    expect(markup).toContain('2026-01-02')

    // 无附件记录展示占位符
    mocks.store.articles = [article({ id: 'doc-2', feishu_attachments: [], local_attachments: [] })]
    act(() => rendered?.root.render(createElement(KnowledgeBasePage)))
    await settle()
    expect(rendered.container.innerHTML).toContain('-')
  })

  it('reports list loading failures', async () => {
    mocks.getKnowledgeArticles.mockRejectedValueOnce(new Error('boom'))
    rendered = renderPage()
    await settle()

    expect(mocks.message.error).toHaveBeenCalledWith('加载知识库列表失败')
  })

  it('opens feishu and local attachments from the table row', async () => {
    rendered = renderPage()
    await settle()

    const previews = Array.from(rendered.container.querySelectorAll('button')).filter(
      (button) => button.textContent === '预览'
    )
    act(() => previews[0]?.click())
    act(() => previews[1]?.click())
    const downloads = Array.from(rendered.container.querySelectorAll('button')).filter(
      (button) => button.textContent === '下载'
    )
    act(() => downloads[0]?.click())
    act(() => downloads[1]?.click())

    expect(openSpy).toHaveBeenCalledWith(
      '/api/v1/safety/knowledge-articles/feishu/records/rec-1/attachments/tok-f/preview',
      '_blank',
      'noopener'
    )
    expect(openSpy).toHaveBeenCalledWith(
      '/api/v1/safety/knowledge-articles/doc-1/attachments/tok-l/content',
      '_blank',
      'noopener'
    )
  })

  it('syncs the feishu mirror and reports created/updated/removed counts', async () => {
    mocks.syncSafetyKnowledge.mockResolvedValueOnce({
      code: 200,
      data: { created: 2, updated: 1, removed: 3, failed: 1 },
    })
    rendered = renderPage()
    await settle()

    act(() => findButton(rendered!.container, '同步飞书法规库')?.click())
    await settle()

    expect(rendered.container.innerHTML).toContain('同步飞书法规库')
    expect(mocks.store.setArticleQueryParams).toHaveBeenCalledWith({ page: 1 })

    mocks.syncSafetyKnowledge.mockResolvedValueOnce({ code: 200, data: { created: 1 } })
    act(() => findButton(rendered!.container, '同步飞书法规库')?.click())
    await settle()

    mocks.syncSafetyKnowledge.mockResolvedValueOnce({ code: 500, message: '飞书未配置' })
    act(() => findButton(rendered!.container, '同步飞书法规库')?.click())
    await settle()
    expect(mocks.message.error).toHaveBeenCalledWith('飞书未配置')
  })

  it('reloads when searching and when the status filter changes', async () => {
    rendered = renderPage()
    await settle()
    mocks.getKnowledgeArticles.mockClear()

    const search = rendered.container.querySelector('input') as HTMLInputElement
    act(() => {
      search.dispatchEvent(new Event('change', { bubbles: true }))
    })
    act(() => findButton(rendered!.container, '查询')?.click())
    await settle()
    expect(mocks.store.setArticleQueryParams).toHaveBeenCalledWith({ page: 1 })

    const select = rendered.container.querySelector('select') as HTMLSelectElement
    Object.defineProperty(select, 'value', { value: '现行有效', configurable: true })
    act(() => {
      select.dispatchEvent(new Event('change', { bubbles: true }))
    })
    await settle()
    expect(mocks.store.setArticleQueryParams).toHaveBeenCalledWith({ page: 1 })

    act(() =>
      (
        rendered!.container.querySelector('button[data-pagination="next"]') as HTMLButtonElement
      )?.click()
    )
    expect(mocks.store.setArticleQueryParams).toHaveBeenCalledWith({ page: 2, page_size: 10 })
  })

  it('creates a document with pending attachments and handles upload failures', async () => {
    mocks.createKnowledgeArticle.mockResolvedValue({ code: 200, data: { id: 'doc-new' } })
    mocks.uploadKnowledgeAttachments.mockResolvedValue({ code: 200, data: { id: 'doc-new' } })
    rendered = renderPage()
    await settle()

    act(() => findButton(rendered!.container, '新建文档')?.click())
    await settle()
    const modalUpload = uploadButton(rendered.container).at(-1)
    act(() => modalUpload?.click())
    expect(mocks.form.resetFields).toHaveBeenCalled()

    act(() => findButton(rendered!.container, '确认')?.click())
    await settle()
    expect(mocks.uploadKnowledgeAttachments).toHaveBeenCalled()
    expect(mocks.store.addArticle).toHaveBeenCalledWith({ id: 'doc-new' })

    // 附件上传失败：文档仍创建，提示 warning
    mocks.uploadKnowledgeAttachments.mockResolvedValueOnce({ code: 500, message: '超限' })
    act(() => findButton(rendered!.container, '新建文档')?.click())
    const retryUpload = uploadButton(rendered.container).at(-1)
    act(() => retryUpload?.click())
    act(() => findButton(rendered!.container, '确认')?.click())
    await settle()
    expect(mocks.message.warning).toHaveBeenCalled()

    // 创建失败分支
    mocks.createKnowledgeArticle.mockResolvedValueOnce({ code: 500, message: '重名' })
    act(() => findButton(rendered!.container, '新建文档')?.click())
    act(() => findButton(rendered!.container, '确认')?.click())
    await settle()
    expect(mocks.message.error).toHaveBeenCalledWith('重名')
  })

  it('edits a mirrored document and keeps feishu attachments read-only', async () => {
    mocks.updateKnowledgeArticle.mockResolvedValue({ code: 200, data: { id: 'doc-1' } })
    rendered = renderPage()
    await settle()

    act(() => findButton(rendered!.container, '编辑')?.click())
    await settle()
    expect(mocks.form.setFieldsValue).toHaveBeenCalled()
    expect(rendered.container.innerHTML).toContain('附件请在多维表格「附件」列中维护')

    act(() => findButton(rendered!.container, '确认')?.click())
    await settle()
    expect(mocks.updateKnowledgeArticle).toHaveBeenCalledWith('doc-1', expect.anything())
    expect(mocks.store.updateArticle).toHaveBeenCalledWith('doc-1', { id: 'doc-1' })

    mocks.updateKnowledgeArticle.mockResolvedValueOnce({ code: 500, message: '编号重复' })
    act(() => findButton(rendered!.container, '编辑')?.click())
    act(() => findButton(rendered!.container, '确认')?.click())
    await settle()
    expect(mocks.message.error).toHaveBeenCalledWith('编号重复')
  })

  it('uploads and removes local attachments while editing', async () => {
    const editable = article({ feishu_record_id: null, feishu_attachments: [] })
    mocks.store.articles = [editable]
    mocks.uploadKnowledgeAttachments.mockResolvedValue({ code: 200, data: editable })
    mocks.deleteKnowledgeAttachment.mockResolvedValue({ code: 200, data: editable })
    rendered = renderPage()
    await settle()

    act(() => findButton(rendered!.container, '编辑')?.click())
    await settle()

    // 编辑弹窗内的本地附件行展示名称与大小
    expect(rendered.container.innerHTML).toContain('本地.pdf')
    expect(rendered.container.innerHTML).toContain('2KB')

    act(() => uploadButton(rendered!.container).at(-1)?.click())
    await settle()
    expect(mocks.uploadKnowledgeAttachments).toHaveBeenCalledWith('doc-1', [expect.any(File)])
    expect(mocks.store.updateArticle).toHaveBeenCalledWith('doc-1', editable)
    expect(mocks.message.success).toHaveBeenCalledWith('附件已上传：sop.pdf')

    // 删除按钮取弹窗内最后一个（表格行也有「删除」）
    const attachmentDelete = () =>
      Array.from(rendered!.container.querySelectorAll('button'))
        .filter((button) => button.textContent?.includes('删除'))
        .at(-1)
    act(() => attachmentDelete()?.click())
    await settle()
    expect(mocks.deleteKnowledgeAttachment).toHaveBeenCalledWith('doc-1', 'tok-l')
    expect(mocks.message.success).toHaveBeenCalledWith('附件已删除')

    // 失败分支：上传与删除
    mocks.uploadKnowledgeAttachments.mockResolvedValueOnce({ code: 500, message: '格式不支持' })
    act(() => uploadButton(rendered!.container).at(-1)?.click())
    await settle()
    expect(mocks.message.error).toHaveBeenCalledWith('格式不支持')

    mocks.deleteKnowledgeAttachment.mockResolvedValueOnce({ code: 500 })
    act(() => attachmentDelete()?.click())
    await settle()
    expect(mocks.message.error).toHaveBeenCalledWith('删除附件失败')
  })

  it('shows the detail drawer with the source link and reports failures', async () => {
    mocks.getKnowledgeArticle.mockResolvedValueOnce({ code: 200, data: article() })
    rendered = renderPage()
    await settle()

    act(() => findButton(rendered!.container, '查看')?.click())
    await settle()
    expect(rendered.container.innerHTML).toContain('法规详情')
    expect(rendered.container.innerHTML).toContain('打开原文链接')

    act(() => findButton(rendered!.container, '关闭')?.click())
    await settle()

    mocks.getKnowledgeArticle.mockRejectedValueOnce(new Error('boom'))
    act(() => findButton(rendered!.container, '查看')?.click())
    await settle()
    expect(mocks.message.error).toHaveBeenCalledWith('获取详情失败')
  })

  it('confirms deletion through the modal and keeps the row on failure', async () => {
    mocks.deleteKnowledgeArticle.mockResolvedValueOnce({ code: 200, data: null })
    rendered = renderPage()
    await settle()

    act(() => findButton(rendered!.container, '删除')?.click())
    expect(mocks.modal.confirm).toHaveBeenCalled()
    const confirmConfig = mocks.modal.confirm.mock.calls[0][0] as { onOk: () => Promise<void> }
    await act(async () => {
      await confirmConfig.onOk()
    })
    expect(mocks.store.removeArticle).toHaveBeenCalledWith('doc-1')

    mocks.deleteKnowledgeArticle.mockResolvedValueOnce({ code: 500, message: '被引用' })
    act(() => findButton(rendered!.container, '删除')?.click())
    const retryConfig = mocks.modal.confirm.mock.calls[1][0] as { onOk: () => Promise<void> }
    await act(async () => {
      await retryConfig.onOk()
    })
    expect(mocks.message.error).toHaveBeenCalledWith('被引用')
  })
})

const radarRun = {
  id: 'run-1',
  status: 'success',
  started_at: '2026-10-06T08:00:00.000Z',
  new_count: 2,
  revised_count: 1,
  failed_count: 0,
  dry_run: false,
}

function radarNotice(container: HTMLElement): HTMLElement | null {
  return container.querySelector('[data-notice="true"]')
}

describe('regulation radar banner', () => {
  it('renders the latest non-dry-run summary without the rules link', async () => {
    mocks.getRadarRuns.mockResolvedValue({
      code: 200,
      data: [radarRun, { ...radarRun, id: 'run-dry', dry_run: true }],
    })
    rendered = renderPage()
    await settle()

    expect(mocks.getRadarRuns).toHaveBeenCalledWith(10)
    const notice = radarNotice(rendered.container)
    expect(notice).not.toBeNull()
    expect(notice?.getAttribute('data-show-rules-link')).toBe('false')
    expect(notice?.textContent).toContain('法规雷达')
    expect(notice?.textContent).toContain('发现新法规 2 部、已修订 1 部')
  })

  it('hides the banner when only dry-run history exists', async () => {
    mocks.getRadarRuns.mockResolvedValue({
      code: 200,
      data: [{ ...radarRun, id: 'run-dry', dry_run: true }],
    })
    rendered = renderPage()
    await settle()

    expect(radarNotice(rendered.container)).toBeNull()
  })

  it('runs a scan through the confirm dialog and refreshes data', async () => {
    mocks.getRadarRuns.mockResolvedValue({ code: 200, data: [radarRun] })
    mocks.runRadarScan.mockResolvedValue({
      code: 200,
      data: { status: 'success', new_count: 3, revised_count: 0 },
    })
    rendered = renderPage()
    await settle()

    act(() => findButton(rendered!.container, '立即扫描')?.click())
    const confirmConfig = mocks.modal.confirm.mock.calls.at(-1)?.[0] as {
      title: string
      onOk: () => Promise<void>
    }
    expect(confirmConfig.title).toContain('立即扫描法规动态')

    await act(async () => {
      await confirmConfig.onOk()
    })
    expect(mocks.runRadarScan).toHaveBeenCalledWith(false)
    expect(mocks.message.success).toHaveBeenCalledWith('扫描完成（success）：新增 3 部、修订 0 部')
    // 扫描后刷新批次与列表
    expect(mocks.getRadarRuns.mock.calls.length).toBeGreaterThan(1)
  })

  it('reports scan failures with the backend message', async () => {
    mocks.getRadarRuns.mockResolvedValue({ code: 200, data: [radarRun] })
    mocks.runRadarScan.mockResolvedValue({ code: 500, message: '抓取源站失败' })
    rendered = renderPage()
    await settle()

    act(() => findButton(rendered!.container, '立即扫描')?.click())
    const confirmConfig = mocks.modal.confirm.mock.calls.at(-1)?.[0] as {
      onOk: () => Promise<void>
    }
    await act(async () => {
      await confirmConfig.onOk()
    })
    expect(mocks.message.error).toHaveBeenCalledWith('抓取源站失败')
  })

  it('opens the run detail with action tags, handles empty and failure results', async () => {
    mocks.getRadarRuns.mockResolvedValue({ code: 200, data: [radarRun] })
    mocks.getRadarRunDetail.mockResolvedValueOnce({
      code: 200,
      data: {
        ...radarRun,
        items: [
          { action: 'new', name: '新法规A', url: 'https://example.com/a' },
          { action: 'revised', name: '法规B', old_date: '2020-01-01', new_date: '2026-01-01' },
          { action: 'obsolete', name: '法规C', reason: '已被替代' },
        ],
      },
    })
    rendered = renderPage()
    await settle()

    act(() => findButton(rendered!.container, '查看明细')?.click())
    await settle()
    expect(mocks.getRadarRunDetail).toHaveBeenCalledWith('run-1')
    const markup = rendered.container.innerHTML
    expect(markup).toContain('新增')
    expect(markup).toContain('已修订')
    expect(markup).toContain('已废止')
    expect(markup).toContain('https://example.com/a')
    expect(markup).toContain('2020-01-01 → 2026-01-01')
    expect(markup).toContain('已被替代')

    mocks.getRadarRunDetail.mockResolvedValueOnce({
      code: 200,
      data: { ...radarRun, items: [] },
    })
    act(() => findButton(rendered!.container, '查看明细')?.click())
    await settle()
    expect(rendered.container.innerHTML).toContain('本批次无明细')

    mocks.getRadarRunDetail.mockResolvedValueOnce({ code: 500, message: '明细读取失败' })
    act(() => findButton(rendered!.container, '查看明细')?.click())
    await settle()
    expect(mocks.message.error).toHaveBeenCalledWith('明细读取失败')
  })
})
