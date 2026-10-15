/* @vitest-environment happy-dom */

import { act, createElement, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  submitWrittenExamGenerate: vi.fn(),
  pollWrittenExamGenerate: vi.fn(),
  extractExamDocumentText: vi.fn(),
  exportWrittenExam: vi.fn(),
}))

const actions = vi.hoisted(() => ({
  resolveDocumentEntryContent: vi.fn(),
}))

const ui = vi.hoisted(() => ({
  message: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}))

vi.mock('@/lib/api/ai', () => api)
vi.mock('@/actions/quality', () => actions)
vi.mock('@/lib/download', () => ({ downloadBytes: vi.fn() }))
vi.mock('@/components/shared/PlatformNotice', () => ({ default: ({ children }: { children?: ReactNode }) => createElement('div', null, children) }))

vi.mock('@ant-design/icons', () => ({
  RobotOutlined: () => null,
  DownloadOutlined: () => null,
  DeleteOutlined: () => null,
  PlusOutlined: () => null,
  UploadOutlined: () => null,
  FileTextOutlined: () => null,
  LoadingOutlined: () => null,
  CloseCircleOutlined: () => null,
}))

vi.mock('antd', async () => {
  const { createElement } = await import('react')
  const Wrapper = ({ children }: { children?: ReactNode }) => createElement('div', null, children)
  const Button = ({
    children,
    disabled,
    loading,
    onClick,
  }: {
    children?: ReactNode
    disabled?: boolean
    loading?: boolean
    onClick?: () => void
  }) => createElement('button', { disabled: disabled || loading, onClick }, children)
  const Input = ({
    value,
    onChange,
    placeholder,
  }: {
    value?: string
    onChange?: (event: { target: { value: string } }) => void
    placeholder?: string
  }) =>
    createElement('input', {
      value: value ?? '',
      placeholder,
      onChange: (event: Event) => onChange?.({ target: { value: (event.target as HTMLInputElement).value } }),
    })
  ;(Input as unknown as Record<string, unknown>).TextArea = Input
  return {
    App: { useApp: () => ({ message: ui.message }) },
    Button,
    Input,
    InputNumber: Input,
    Space: Wrapper,
    Spin: Wrapper,
    Tag: ({ children }: { children?: ReactNode }) => createElement('span', null, children),
  }
})

import AiWrittenExamClient from './AiWrittenExamClient'
import type { AiWrittenExamPayload, TrainingSessionData } from '@/types/hr'

const sessionData: TrainingSessionData = { topic: 'GMP培训' }

const emptyPayload: AiWrittenExamPayload = {
  files: [],
  uploaded_content: '',
  manual_content: '',
  single_choice_count: 5,
  multiple_choice_count: 0,
  true_false_count: 0,
  fill_blank_count: 5,
  choice_questions: [],
  true_false_questions: [],
  fill_blank_questions: [],
}

/** happy-dom 下构造可被 Array.from 展开的类 FileList 对象并触发 change */
const selectFiles = async (container: HTMLElement, names: string[]) => {
  const input = container.querySelector('input[type="file"]') as HTMLInputElement
  expect(input).toBeTruthy()
  const files = names.map((n) => new File([`素材-${n}`], n, { type: 'text/plain' }))
  const fileList: FileList = Object.assign(
    { length: files.length, item: (i: number) => files[i] ?? null },
    Object.fromEntries(files.map((f, i) => [i, f])),
  ) as unknown as FileList
  Object.defineProperty(input, 'files', { value: fileList, configurable: true })
  await act(async () => {
    input.dispatchEvent(new Event('change', { bubbles: true }))
  })
  await act(async () => { await Promise.resolve() })
}

const clickGenerate = async (container: HTMLElement) => {
  const btn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('AI 出题'))
  expect(btn).toBeTruthy()
  await act(async () => {
    btn?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  })
}

const lastGeneratePayload = () =>
  api.submitWrittenExamGenerate.mock.calls[0][0] as {
    files: { name: string; code: string | null; content: string }[]
    uploaded_content: string
  }

describe('AiWrittenExamClient 上传份数与出题素材通道', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    vi.clearAllMocks()
    api.submitWrittenExamGenerate.mockResolvedValue('job-1')
    api.pollWrittenExamGenerate.mockResolvedValue({ choice_questions: [], true_false_questions: [], fill_blank_questions: [] })
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
  })

  const render = (props: Record<string, unknown> = {}) => {
    act(() => {
      root.render(
        createElement(AiWrittenExamClient, {
          sessionData,
          ...props,
        } as never),
      )
    })
  }

  it('一次选择 5 份文件全部保留（回归：不再只保留 3 份）', async () => {
    const names = ['a.docx', 'b.pdf', 'c.txt', 'd.md', 'e.wps']
    api.extractExamDocumentText.mockImplementation((file: File) =>
      Promise.resolve({ text: `素材-${file.name}`, filename: file.name }),
    )
    render()
    await selectFiles(container, names)
    for (const name of names) {
      expect(container.textContent).toContain(name)
    }
    expect(container.textContent).toContain('已上传 5 份')
  })

  it('分次续传不挤掉已上传文件（回归：旧 slice(-2) 截断）', async () => {
    api.extractExamDocumentText.mockImplementation((file: File) =>
      Promise.resolve({ text: `素材-${file.name}`, filename: file.name }),
    )
    render()
    await selectFiles(container, ['first.docx', 'second.docx'])
    await selectFiles(container, ['third.docx', 'fourth.docx'])
    for (const name of ['first.docx', 'second.docx', 'third.docx', 'fourth.docx']) {
      expect(container.textContent).toContain(name)
    }
  })

  it('出题请求：逐份上传并入 files 通道且 uploaded_content 为空（后端可按文件分批并行）', async () => {
    api.extractExamDocumentText.mockImplementation((file: File) =>
      Promise.resolve({ text: `素材-${file.name}`, filename: file.name }),
    )
    render()
    await selectFiles(container, ['sop-a.docx', 'sop-b.pdf'])
    await clickGenerate(container)
    expect(api.submitWrittenExamGenerate).toHaveBeenCalledTimes(1)
    const payload = lastGeneratePayload()
    expect(payload.uploaded_content).toBe('')
    const uploaded = payload.files.filter((f) => f.name.startsWith('sop-'))
    expect(uploaded.map((f) => f.name)).toEqual(['sop-a.docx', 'sop-b.pdf'])
    expect(uploaded.map((f) => f.content)).toEqual(['素材-sop-a.docx', '素材-sop-b.pdf'])
    expect(uploaded.every((f) => f.code === null)).toBe(true)
  })

  it('单份解析文本超 3 万字时按上限截断进入出题素材', async () => {
    api.extractExamDocumentText.mockResolvedValue({ text: 'x'.repeat(40000), filename: 'big.pdf' })
    render()
    await selectFiles(container, ['big.pdf'])
    expect(container.textContent).toContain('仅前 3 万字用于出题')
    await clickGenerate(container)
    const payload = lastGeneratePayload()
    expect(payload.files).toHaveLength(1)
    expect(payload.files[0].content.length).toBe(30000)
  })

  it('草稿恢复的合并上传内容仍走 uploaded_content 通道（12 万字符预算，不并入 files）', async () => {
    render({ initialPayload: { ...emptyPayload, uploaded_content: '历史合并的草稿上传内容' } })
    await clickGenerate(container)
    expect(api.submitWrittenExamGenerate).toHaveBeenCalledTimes(1)
    const payload = lastGeneratePayload()
    expect(payload.uploaded_content).toContain('历史合并的草稿上传内容')
    expect(payload.files).toEqual([])
  })
})
