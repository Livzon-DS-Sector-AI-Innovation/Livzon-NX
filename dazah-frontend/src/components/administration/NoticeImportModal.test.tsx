/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const actionsMock = vi.hoisted(() => ({
  parseNoticeAction: vi.fn(),
  importNoticeAction: vi.fn(),
}))

const mocks = vi.hoisted(() => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  // 记录 Dragger 的 beforeUpload / onRemove 供测试直调（绕开 rc-upload 浏览器依赖）
  beforeUpload: vi.fn(),
  onRemove: vi.fn(),
}))

vi.mock('@/actions/administration', () => actionsMock)

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>()
  const { createElement } = await import('react')
  return {
    ...actual,
    // 组件里的 message 来自 antd 的全局通知：它会创建独立 React root，并为每条
    // 提示挂一个约 3 秒的自动关闭定时器。用例若在该定时器到期前结束，定时器会在
    // happy-dom 环境销毁之后触发渲染，抛 "ReferenceError: window is not defined"，
    // 让整次测试以未处理错误失败（用例本身全部通过）。这里只替换副作用边界，
    // 保留 antd 其余组件与主题的真实实现。
    message: mocks.message,
    App: { ...actual.App, useApp: () => ({ message: mocks.message }) },
    // rc-upload 在 happy-dom 留下未完成的 fetch/timer：Dragger 用纯渲染 stub
    Upload: {
      ...actual.Upload,
      Dragger: (props: Record<string, unknown>) => {
        mocks.beforeUpload = props.beforeUpload as never
        mocks.onRemove = props.onRemove as never
        return createElement(
          'div',
          { 'data-testid': 'dragger' },
          props.children as never,
        )
      },
    },
  }
})

import NoticeImportModal from './NoticeImportModal'

let container: HTMLDivElement
let root: Root
const onClose = vi.fn()
const onImported = vi.fn()

function render() {
  act(() => {
    root.render(
      <NoticeImportModal open onClose={onClose} onImported={onImported} />,
    )
  })
}

/** 轮询到条件成立（带真实时间让出：Modal/表单渲染依赖动画帧与定时器）。 */
async function until(condition: () => boolean, message: string) {
  for (let i = 0; i < 60; i += 1) {
    if (condition()) return
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 25))
    })
  }
  throw new Error(message)
}

function bodyText(): string {
  return document.body.textContent || ''
}

function button(text: string): HTMLButtonElement | undefined {
  const needle = text.replace(/\s/g, '')
  // antd 两字按钮会在字间插入空格（如「取 消」），统一去空白再匹配
  return [...document.body.querySelectorAll('button')].find((b) =>
    (b.textContent ?? '').replace(/\s/g, '').includes(needle),
  )
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

/** 选文件并等 AI 识别结果预填进表单。 */
async function upload(file: File) {
  expect(typeof mocks.beforeUpload).toBe('function')
  await act(async () => {
    await mocks.beforeUpload(file)
  })
}

describe('NoticeImportModal', () => {
  beforeEach(() => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    render()
  })

  afterEach(async () => {
    await act(async () => {
      root.unmount()
    })
    // 卸载后让出一轮宏任务：React 调度器里排队的被动副作用必须在
    // happy-dom 环境销毁之前执行完
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
    container.remove()
    document.body.innerHTML = ''
    vi.clearAllMocks()
  })

  it('渲染上传区与操作提示（无文件时无「确认导入」按钮）', async () => {
    await until(
      () => bodyText().includes('点击或拖拽公告文件到此处'),
      '上传区未渲染',
    )
    expect(bodyText()).toContain('上传公告（AI 识别元数据）')
    expect(button('确认导入')).toBeUndefined()
    expect(button('取消')).toBeUndefined()
  })

  it('解析成功：预填表单并展示识别结果', async () => {
    actionsMock.parseNoticeAction.mockResolvedValue({
      code: 200,
      data: PREVIEW,
    })
    const file = makeFile('notice.pdf')
    await upload(file)

    await until(() => bodyText().includes('公告编号'), '识别结果表单未渲染')
    expect(actionsMock.parseNoticeAction).toHaveBeenCalledWith(file)
    const inputValues = [...document.body.querySelectorAll('input')]
      .map((input) => input.value)
      .join('|')
    expect(inputValues).toContain('Notice-2026-001')
    expect(inputValues).toContain('年度安全培训通知')
    expect(mocks.message.error).not.toHaveBeenCalled()
    // 选中文件后出现确认导入与取消按钮
    expect(button('确认导入')).toBeTruthy()
  })

  it('移除已选文件：清空文件与识别结果，回到初始上传态', async () => {
    actionsMock.parseNoticeAction.mockResolvedValue({
      code: 200,
      data: PREVIEW,
    })
    await upload(makeFile('notice.pdf'))
    await until(() => button('确认导入') !== undefined, '确认导入按钮未出现')

    await act(async () => {
      mocks.onRemove()
    })

    await until(() => button('确认导入') === undefined, '移除文件后未清空')
    expect(bodyText()).not.toContain('Notice-2026-001')
    expect(bodyText()).toContain('点击或拖拽公告文件到此处')
    expect(actionsMock.importNoticeAction).not.toHaveBeenCalled()
  })

  it('解析失败：提示后端错误且不预填', async () => {
    actionsMock.parseNoticeAction.mockResolvedValue({
      code: 500,
      message: 'AI 服务未配置',
    })
    await upload(makeFile('notice.docx'))

    await until(
      () => mocks.message.error.mock.calls.length > 0,
      '解析失败未提示',
    )
    expect(mocks.message.error).toHaveBeenCalledWith('AI 服务未配置')
    const inputValues = [...document.body.querySelectorAll('input')]
      .map((input) => input.value)
      .join('|')
    expect(inputValues).not.toContain('Notice-2026-001')
  })

  it('解析失败且后端无文案：回退通用提示', async () => {
    actionsMock.parseNoticeAction.mockResolvedValue({ code: 500 })
    await upload(makeFile('notice.pdf'))

    await until(
      () => mocks.message.error.mock.calls.length > 0,
      '解析失败未提示',
    )
    expect(mocks.message.error).toHaveBeenCalledWith(
      '识别失败，请重试或手动填写后导入',
    )
  })

  it('非法扩展名：提示仅支持指定格式且不触发解析', async () => {
    await upload(makeFile('notice.txt'))

    expect(mocks.message.error).toHaveBeenCalledWith(
      '仅支持 PDF/Word/图片格式的公告文件',
    )
    expect(actionsMock.parseNoticeAction).not.toHaveBeenCalled()
    expect(button('确认导入')).toBeUndefined()
  })

  it('超大文件：提示超过 30MB 且不触发解析', async () => {
    await upload(makeFile('big.pdf', 31 * 1024 * 1024))

    expect(mocks.message.error).toHaveBeenCalledWith('公告文件不能超过 30MB')
    expect(actionsMock.parseNoticeAction).not.toHaveBeenCalled()
    expect(button('确认导入')).toBeUndefined()
  })

  it('确认导入：携带识别出的元数据提交，成功后提示并通知父级', async () => {
    actionsMock.parseNoticeAction.mockResolvedValue({
      code: 200,
      data: PREVIEW,
    })
    actionsMock.importNoticeAction.mockResolvedValue({
      code: 200,
      data: { id: 'n-9' },
    })
    const file = makeFile('notice.pdf')
    await upload(file)
    await until(() => button('确认导入') !== undefined, '确认导入按钮未出现')

    await act(async () => {
      button('确认导入')!.click()
    })

    await until(() => onImported.mock.calls.length > 0, '导入成功未通知父级')
    expect(actionsMock.importNoticeAction).toHaveBeenCalledWith(
      file,
      expect.objectContaining({
        notice_no: 'Notice-2026-001',
        title: '年度安全培训通知',
        publisher: '安全环保部',
        published_at: '2026-11-20',
        category: '通知',
        remark: '全员参加',
      }),
    )
    expect(mocks.message.success).toHaveBeenCalledWith(
      '公告已录入台账（内容已识别归档，可查看原文存档）',
    )
    // 成功后表单重置：文件清空，确认导入按钮消失
    await until(
      () => button('确认导入') === undefined,
      '导入成功后未重置表单',
    )
    expect(onClose).not.toHaveBeenCalled()
  })

  it('导入失败：提示后端错误，保留表单且不通知父级', async () => {
    actionsMock.parseNoticeAction.mockResolvedValue({
      code: 200,
      data: PREVIEW,
    })
    actionsMock.importNoticeAction.mockResolvedValue({
      code: 409,
      message: '公告编号已存在',
    })
    await upload(makeFile('notice.pdf'))
    await until(() => button('确认导入') !== undefined, '确认导入按钮未出现')

    await act(async () => {
      button('确认导入')!.click()
    })

    await until(() => mocks.message.error.mock.calls.length > 0, '导入失败未提示')
    expect(mocks.message.error).toHaveBeenCalledWith('公告编号已存在')
    expect(mocks.message.success).not.toHaveBeenCalled()
    expect(onImported).not.toHaveBeenCalled()
    // 表单保留，用户可修正后重试
    expect(button('确认导入')).toBeTruthy()
  })

  it('取消：重置表单并关闭弹窗', async () => {
    actionsMock.parseNoticeAction.mockResolvedValue({
      code: 200,
      data: PREVIEW,
    })
    await upload(makeFile('notice.pdf'))
    await until(() => button('取消') !== undefined, '取消按钮未出现')

    await act(async () => {
      button('取消')!.click()
    })

    expect(onClose).toHaveBeenCalledTimes(1)
    expect(onImported).not.toHaveBeenCalled()
    expect(actionsMock.importNoticeAction).not.toHaveBeenCalled()
  })
})
