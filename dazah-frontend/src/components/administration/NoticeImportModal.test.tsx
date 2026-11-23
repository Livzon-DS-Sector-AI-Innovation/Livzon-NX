/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const actionsMock = vi.hoisted(() => ({
  parseNoticeAction: vi.fn(),
  importNoticeAction: vi.fn(),
}))

vi.mock('@/actions/administration', () => actionsMock)

// 记录 Dragger 的 beforeUpload 供测试直调（绕开 rc-upload 浏览器依赖）
const uploadMocks = vi.hoisted(() => ({ beforeUpload: vi.fn() }))

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>()
  const { createElement } = await import('react')
  return {
    ...actual,
    Upload: {
      ...actual.Upload,
      Dragger: (props: Record<string, unknown>) => {
        // 组件挂载时保存 beforeUpload（rc-upload 正常路径也会回调它）
        uploadMocks.beforeUpload = props.beforeUpload as never
        return createElement(
          'div',
          { 'data-testid': 'dragger' },
          props.children as never,
        )
      },
    },
  }
})

import { App as AntdApp } from 'antd'

import NoticeImportModal from './NoticeImportModal'

let container: HTMLDivElement
let root: Root
const onClose = vi.fn()
const onImported = vi.fn()

function render() {
  act(() => {
    root.render(
      <AntdApp>
        <NoticeImportModal open onClose={onClose} onImported={onImported} />
      </AntdApp>,
    )
  })
}

const PREVIEW = {
  notice_no: 'Notice-2026-001',
  title: '年度安全培训通知',
  publisher: '安全环保部',
  published_at: '2026-11-20',
  category: '通知',
  remark: '全员参加',
  pages: 3,
  suggestion: {
    notice_no: 'Notice-2026-001',
    title: '年度安全培训通知',
    publisher: '安全环保部',
    published_at: '2026-11-20',
    category: '通知',
    remark: '全员参加',
  },
}

function makeFile(name: string, size = 1024): File {
  const file = new File(['content'], name, { type: 'application/pdf' })
  Object.defineProperty(file, 'size', { value: size })
  return file
}

describe('NoticeImportModal', () => {
  beforeEach(() => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container, {
      onUncaughtError: (error: unknown) => {
        // eslint-disable-next-line no-console
        console.log('DBG uncaught:', error)
      },
    })
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    vi.clearAllMocks()
  })

  it('渲染上传区与操作提示（无文件时 footer 为空）', () => {
    render()
    const text = document.body.textContent || ''
    expect(text).toContain('上传公告（AI 识别元数据）')
    expect(text).toContain('点击或拖拽公告文件到此处')
    // 未选文件时 footer=null：无「确认导入」按钮
    expect(
      [...document.body.querySelectorAll('button')].some((b) =>
        b.textContent?.includes('确认导入'),
      ),
    ).toBe(false)
  })

  it('解析成功：预填表单并展示识别结果', async () => {
    actionsMock.parseNoticeAction.mockResolvedValue({
      code: 200,
      data: PREVIEW,
    })
    render()
    expect(typeof uploadMocks.beforeUpload).toBe('function')

    await act(async () => {
      await uploadMocks.beforeUpload(makeFile('notice.pdf'))
      await new Promise((r) => setTimeout(r, 30))
    })

    expect(actionsMock.parseNoticeAction).toHaveBeenCalled()
    expect(document.body.textContent).toContain('公告编号')
    const inputValues = [...document.body.querySelectorAll('input')]
      .map((i) => i.value)
      .join('|')
    expect(inputValues).toContain('Notice-2026-001')
  })

  it('解析失败：提示识别失败且不预填', async () => {
    actionsMock.parseNoticeAction.mockResolvedValue({
      code: 500,
      message: 'AI 服务未配置',
    })
    render()
    await act(async () => {
      await uploadMocks.beforeUpload(makeFile('notice.docx'))
      await new Promise((r) => setTimeout(r, 30))
    })
    expect(document.body.textContent).not.toContain('Notice-2026-001')
  })
})


describe('NoticeImportModal 上传校验与导入', () => {
  beforeEach(() => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    render()
  })

  it('非法扩展名：提示仅支持指定格式且不触发解析', async () => {
    await act(async () => {
      await uploadMocks.beforeUpload(makeFile('notice.txt'))
    })
    expect(actionsMock.parseNoticeAction).not.toHaveBeenCalled()
    expect(
      [...document.body.querySelectorAll('button')].some((b) =>
        b.textContent?.includes('确认导入'),
      ),
    ).toBe(false)
  })

  it('超大文件：提示超过 30MB', async () => {
    await act(async () => {
      await uploadMocks.beforeUpload(makeFile('big.pdf', 31 * 1024 * 1024))
    })
    expect(actionsMock.parseNoticeAction).not.toHaveBeenCalled()
    expect(document.body.textContent).toContain('不能超过 30MB')
  })

  it('解析成功后出现确认导入按钮：点击走导入成功链并触发回调', async () => {
    actionsMock.parseNoticeAction.mockResolvedValue({
      code: 200,
      data: PREVIEW,
    })
    await act(async () => {
      await uploadMocks.beforeUpload(makeFile('notice.pdf'))
      await new Promise((r) => setTimeout(r, 30))
    })
    actionsMock.importNoticeAction.mockResolvedValue({
      code: 200,
      data: { id: 'n-9' },
    })

    const importBtn = [...document.body.querySelectorAll('button')].find((b) =>
      b.textContent?.includes('确认导入'),
    )
    expect(importBtn).toBeTruthy()
    await act(async () => {
      importBtn!.click()
      await new Promise((r) => setTimeout(r, 30))
    })
    expect(actionsMock.importNoticeAction).toHaveBeenCalled()
    expect(onImported).toHaveBeenCalled()
  })

  it('导入失败：提示错误且不触发回调', async () => {
    actionsMock.parseNoticeAction.mockResolvedValue({
      code: 200,
      data: PREVIEW,
    })
    await act(async () => {
      await uploadMocks.beforeUpload(makeFile('notice.pdf'))
      await new Promise((r) => setTimeout(r, 30))
    })
    actionsMock.importNoticeAction.mockResolvedValue({
      code: 409,
      message: '公告编号已存在',
    })

    const importBtn = [...document.body.querySelectorAll('button')].find((b) =>
      b.textContent?.includes('确认导入'),
    )
    await act(async () => {
      importBtn!.click()
      await new Promise((r) => setTimeout(r, 30))
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 100))
    })
    expect(document.body.textContent).toContain('公告编号已存在')
  })
})
