/* @vitest-environment happy-dom */

import { act, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })

const actions = vi.hoisted(() => ({
  parseHazardLedgerImport: vi.fn(),
  importHazardLedger: vi.fn(),
}))

const ui = vi.hoisted(() => ({
  message: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}))

vi.mock('@/actions/safety', () => actions)

vi.mock('@/components/shared/PlatformNotice', async () => {
  const { createElement } = await import('react')
  return {
    default: ({
      message,
      description,
    }: {
      message: ReactNode
      description?: ReactNode
    }) => createElement('div', null, message, description),
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
      children
    )
  const Text = ({ children }: { children?: ReactNode }) =>
    createElement('span', null, children)
  const Space = ({ children }: { children?: ReactNode }) =>
    createElement('div', null, children)
  Space.Compact = ({ children }: { children?: ReactNode }) =>
    createElement('div', null, children)
  return {
    Alert: ({ message: msg, description }: { message: ReactNode; description?: ReactNode }) =>
      createElement('div', null, msg, description),
    App: { useApp: () => ({ message: ui.message }) },
    Button,
    Input: ({ value, onChange, placeholder }: { value?: string; onChange?: (e: { target: { value: string } }) => void; placeholder?: string }) =>
      createElement('input', { value, placeholder, onChange }),
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
    Table: ({ dataSource }: { dataSource?: Array<{ name: string }> }) =>
      createElement(
        'div',
        null,
        (dataSource || []).map((row) => createElement('div', { key: row.name }, row.name))
      ),
    Tag: ({ children }: { children?: ReactNode }) => createElement('span', null, children),
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
              const fake = { name: '作业活动分级管控总清单101-102.xlsx', size: 1024 }
              beforeUpload?.(fake, [fake])
            },
          },
          '上传'
        ),
    },
  }
})

vi.mock('@ant-design/icons', () => ({
  ImportOutlined: () => null,
  InboxOutlined: () => null,
  ReloadOutlined: () => null,
}))

import HazardLedgerImportModal from './HazardLedgerImportModal'

const PREVIEW = {
  filename: '作业活动分级管控总清单101-102.xlsx',
  department_guess: '101-102车间',
  total_valid_rows: 2,
  sheets: [
    {
      name: '消毒',
      format: 'activity',
      format_label: '作业活动分级管控清单',
      row_count: 2,
      skipped: false,
      skip_reason: null,
      sample_rows: [
        {
          name: '罐内发酵',
          step: '打开进料阀门',
          hazard_desc: '管道憋压',
          accident: '其他伤害',
          l: 1,
          e: 6,
          c: 1,
          d: 6,
          level: '四级/低风险',
          engineering: null,
        },
      ],
      errors: [],
    },
    {
      name: '风险点总计',
      format: null,
      format_label: null,
      row_count: 0,
      skipped: true,
      skip_reason: '无法识别的表格格式',
      sample_rows: [],
      errors: [],
    },
  ],
}

function findButton(container: HTMLElement, text: string): HTMLButtonElement {
  const buttons = Array.from(container.querySelectorAll('button'))
  const matched = buttons.find((btn) => btn.textContent?.includes(text))
  if (!matched) {
    throw new Error(`button ${text} not found; got ${buttons.map((b) => b.textContent)}`)
  }
  return matched as HTMLButtonElement
}

describe('HazardLedgerImportModal', () => {
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
  })

  function render() {
    act(() => {
      root.render(
        <HazardLedgerImportModal open onClose={onClose} onImported={onImported} />
      )
    })
  }

  it('解析成功后展示子表与默认部门，导入时传递所选子表', async () => {
    actions.parseHazardLedgerImport.mockResolvedValue({ code: 200, data: PREVIEW })
    actions.importHazardLedger.mockResolvedValue({
      code: 200,
      data: {
        imported: 2,
        skipped_existing: 0,
        duplicate_in_file: 0,
        failed_sheets: [],
        row_errors: [],
        archive_path: 'uploads/safety/hazard-import/a.xlsx',
      },
    })
    render()

    await act(async () => {
      findButton(container, '上传').click()
    })
    expect(actions.parseHazardLedgerImport).toHaveBeenCalledTimes(1)

    // 子表名与默认部门推断文案出现；跳过的子表不可选
    expect(container.textContent).toContain('消毒')
    const deptInput = container.querySelector('input') as HTMLInputElement
    expect(deptInput.value).toBe('101-102车间')
    expect(container.textContent).toContain('识别到 2 个子表')

    await act(async () => {
      findButton(container, '导入选中子表').click()
    })
    expect(actions.importHazardLedger).toHaveBeenCalledWith(
      expect.objectContaining({ name: '作业活动分级管控总清单101-102.xlsx' }),
      '101-102车间',
      ['消毒']
    )

    // 结果视图 + 完成回调
    expect(container.textContent).toContain('成功导入 2 条危险源辨识记录')
    await act(async () => {
      findButton(container, '完成').click()
    })
    expect(onImported).toHaveBeenCalledTimes(1)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('解析失败时提示错误且不进入预览', async () => {
    actions.parseHazardLedgerImport.mockResolvedValue({
      code: 400,
      message: '仅支持 .xlsx, .xls 格式文件',
    })
    render()

    await act(async () => {
      findButton(container, '上传').click()
    })
    expect(ui.message.error).toHaveBeenCalledWith('仅支持 .xlsx, .xls 格式文件')
    expect(container.textContent).not.toContain('识别到')
  })

  it('未选择文件时导入按钮不可用', () => {
    render()
    const importButton = findButton(container, '导入选中子表')
    expect(importButton.disabled).toBe(true)
  })
})
