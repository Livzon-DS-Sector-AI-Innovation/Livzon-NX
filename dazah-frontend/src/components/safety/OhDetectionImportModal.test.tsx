/* @vitest-environment happy-dom */

import { act, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })

const actions = vi.hoisted(() => ({
  parseOhDetectionReport: vi.fn(),
  importOhDetectionReport: vi.fn(),
}))

const ui = vi.hoisted(() => ({
  message: { error: vi.fn(), success: vi.fn() },
}))

vi.mock('@/actions/safety', () => actions)

vi.mock('@/components/shared/PlatformNotice', async () => {
  const { createElement } = await import('react')
  return {
    default: ({ message }: { message: ReactNode }) =>
      createElement('div', null, message),
  }
})

vi.mock('antd', async () => {
  const { createElement } = await import('react')
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
  }) =>
    createElement(
      'button',
      { disabled: disabled || loading, onClick, type: 'button' },
      children,
    )
  const Text = ({ children }: { children?: ReactNode }) =>
    createElement('span', null, children)
  const Space = ({ children }: { children?: ReactNode }) =>
    createElement('div', null, children)
  return {
    App: { useApp: () => ({ message: ui.message }) },
    Button,
    Collapse: ({ items }: { items?: Array<{ key: string; label: ReactNode; children: ReactNode }> }) =>
      createElement(
        'div',
        null,
        (items || []).map((item) =>
          createElement('div', { key: item.key }, item.label, item.children),
        ),
      ),
    Descriptions: ({ items }: { items?: Array<{ key: string; label: ReactNode; children: ReactNode }> }) =>
      createElement(
        'div',
        null,
        (items || []).map((item) =>
          createElement('div', { key: item.key }, item.label, ':', item.children),
        ),
      ),
    Form: Object.assign(
      ({ children }: { children?: ReactNode }) => createElement('form', null, children),
      {
        Item: ({
          label,
          children,
          name,
        }: {
          label?: ReactNode
          children?: ReactNode
          name?: string
        }) => createElement('label', { 'data-field': name }, label, children),
        useForm: () => [
          {
            setFieldsValue: vi.fn(),
            resetFields: vi.fn(),
            validateFields: async () => ({
              report_no: 'NZXZW-J-2026-141',
              company_name: '丽珠集团（宁夏）制药有限公司',
            }),
          },
        ],
      },
    ),
    Input: Object.assign(() => createElement('input'), {
      TextArea: () => createElement('textarea'),
    }),
    Modal: ({
      open,
      title,
      children,
      footer,
    }: {
      open: boolean
      title?: ReactNode
      children?: ReactNode
      footer?: ReactNode
    }) => (open ? createElement('div', null, title, children, footer) : null),
    Space,
    Spin: () => createElement('div', null, 'loading'),
    Tag: ({ children }: { children?: ReactNode }) =>
      createElement('span', null, children),
    Typography: { Text },
    Upload: {
      Dragger: ({
        beforeUpload,
      }: {
        beforeUpload?: (file: unknown, files: unknown[]) => unknown
      }) =>
        createElement(
          'button',
          {
            type: 'button',
            'data-testid': 'upload-trigger',
            onClick: () => {
              const injected = (
                globalThis as { __uploadFile?: { name: string; size: number } }
              ).__uploadFile
              const fake = injected ?? { name: 'report.pdf', size: 2048 }
              beforeUpload?.(fake, [fake])
            },
          },
          '上传',
        ),
    },
  }
})

vi.mock('@ant-design/icons', () => ({
  InboxOutlined: () => null,
  FilePdfOutlined: () => null,
}))

import OhDetectionImportModal from './OhDetectionImportModal'
import type { OhDetectionParsePreview } from '@/types/safety'

const PREVIEW: OhDetectionParsePreview = {
  report_no: 'NZXZW-J-2026-141',
  report_name: '职业病危害因素检测报告',
  company_name: '丽珠集团（宁夏）制药有限公司',
  detection_agency: '宁夏智信安全技术检测有限公司',
  file_name: 'report.pdf',
  file_sha256: 'abc',
  parse_mode: 'rules',
  table_count: 2,
  total_points: 10,
  exceed_points: 1,
  noise_post_points: 5,
  warnings: [],
  tables: [
    {
      table_ref: '表5-2',
      table_title: '定点粉尘（总尘）检测结果一览表',
      layout: 'dust_total',
      mode: 'rules',
      row_count: 5,
      warnings: [],
      sample_rows: [],
    },
    {
      table_ref: '表9-1',
      table_title: '未知版式表',
      layout: 'unknown',
      mode: 'skipped',
      row_count: 0,
      warnings: ['版式未识别且未配置 AI 模型'],
      sample_rows: [],
    },
  ],
  existing_report_id: 'r-9',
  existing_total_points: 8,
}

describe('OhDetectionImportModal', () => {
  let container: HTMLDivElement
  let root: Root
  const onClose = vi.fn()
  const onImported = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    delete (globalThis as { __uploadFile?: unknown }).__uploadFile
  })

  function renderModal() {
    act(() => {
      root.render(
        <OhDetectionImportModal open onClose={onClose} onImported={onImported} />,
      )
    })
  }

  function findButton(text: string): HTMLButtonElement {
    const matched = Array.from(container.querySelectorAll('button')).find((btn) =>
      btn.textContent?.includes(text),
    )
    if (!matched) {
      throw new Error(`button ${text} not found; got ${Array.from(container.querySelectorAll('button')).map((b) => b.textContent)}`)
    }
    return matched as HTMLButtonElement
  }

  function upload() {
    return act(async () => {
      findButton('上传').click()
    })
  }

  it('上传后展示解析预览与覆盖提示', async () => {
    actions.parseOhDetectionReport.mockResolvedValue({
      code: 200,
      message: 'success',
      data: PREVIEW,
    })
    renderModal()
    await upload()
    expect(container.textContent).toContain('识别表格:2 张')
    expect(container.textContent).toContain('检测记录:10 条')
    expect(container.textContent).toContain('表5-2')
    expect(container.textContent).toContain('规则识别')
    expect(container.textContent).toContain('跳过')
    expect(container.textContent).toContain(
      '报告编号已存在，导入将覆盖原 8 条检测明细',
    )
    expect(findButton('确认导入')).toBeTruthy()
  })

  it('解析失败提示错误且不出现确认按钮', async () => {
    actions.parseOhDetectionReport.mockResolvedValue({
      code: 422,
      message: '未识别到文本内容，疑似扫描件',
    })
    renderModal()
    await upload()
    expect(ui.message.error).toHaveBeenCalledWith(
      expect.stringContaining('扫描件'),
    )
    expect(container.textContent).not.toContain('确认导入')
  })

  it('确认导入提交解析元数据并回调刷新', async () => {
    actions.parseOhDetectionReport.mockResolvedValue({
      code: 200,
      message: 'success',
      data: { ...PREVIEW, existing_report_id: null },
    })
    actions.importOhDetectionReport.mockResolvedValue({
      code: 200,
      message: 'success',
      data: {
        report: { id: 'r-1' },
        imported_count: 10,
        replaced: false,
        monitors_synced: 3,
        skipped_tables: [{ table: '表9-1 未知版式表', reason: '版式未识别' }],
      },
    })
    renderModal()
    await upload()
    await act(async () => {
      findButton('确认导入').click()
    })
    const call = actions.importOhDetectionReport.mock.calls[0]
    expect(call[0]).toMatchObject({ name: 'report.pdf' })
    expect(call[1].report_no).toBe('NZXZW-J-2026-141')
    expect(ui.message.success).toHaveBeenCalledWith(
      expect.stringContaining('已同步 3 条车间监测记录'),
    )
    expect(onImported).toHaveBeenCalled()
  })

  it('导入失败保留预览供重试', async () => {
    actions.parseOhDetectionReport.mockResolvedValue({
      code: 200,
      message: 'success',
      data: { ...PREVIEW, existing_report_id: null },
    })
    actions.importOhDetectionReport.mockResolvedValue({
      code: 429,
      message: '模型调用触发限流，请稍后重试',
    })
    renderModal()
    await upload()
    await act(async () => {
      findButton('确认导入').click()
    })
    expect(ui.message.error).toHaveBeenCalled()
    expect(container.textContent).toContain('确认导入')
    expect(onImported).not.toHaveBeenCalled()
  })

  it('非 PDF 文件直接拒绝', async () => {
    renderModal()
    ;(globalThis as { __uploadFile?: { name: string; size: number } }).__uploadFile = {
      name: 'report.doc',
      size: 2048,
    }
    await upload()
    expect(ui.message.error).toHaveBeenCalledWith('仅支持 PDF 格式的检测报告')
    expect(actions.parseOhDetectionReport).not.toHaveBeenCalled()
  })

  it('超过 30MB 的 PDF 拒绝解析', async () => {
    renderModal()
    ;(globalThis as { __uploadFile?: { name: string; size: number } }).__uploadFile = {
      name: 'report.pdf',
      size: 31 * 1024 * 1024,
    }
    await upload()
    expect(ui.message.error).toHaveBeenCalledWith('检测报告文件不能超过 30MB')
    expect(actions.parseOhDetectionReport).not.toHaveBeenCalled()
  })
})
