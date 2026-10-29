/* @vitest-environment happy-dom */

import { act, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })

const actions = vi.hoisted(() => ({
  getOhDetectionReports: vi.fn(),
  getOhDetectionResults: vi.fn(),
  deleteOhDetectionReport: vi.fn(),
}))

const permState = vi.hoisted(() => ({
  canOperate: true,
  canImport: true,
  canDelete: true,
}))

const ui = vi.hoisted(() => ({
  message: { error: vi.fn(), success: vi.fn() },
}))

vi.mock('@/actions/safety', () => ({
  ...actions,
}))

vi.mock('@/hooks/usePagePermissions', () => ({
  usePagePermissions: () => permState,
}))

vi.mock('@/components/safety/OhDetectionImportModal', () => ({
  default: () => null,
}))

vi.mock('antd', async () => {
  const { createElement } = await import('react')
  const Button = ({
    children,
    disabled,
    loading,
    onClick,
    danger,
  }: {
    children?: ReactNode
    disabled?: boolean
    loading?: boolean
    onClick?: () => void
    danger?: boolean
  }) =>
    createElement(
      'button',
      { disabled: disabled || loading, onClick, type: 'button', 'data-danger': danger },
      children
    )
  const Text = ({ children, type }: { children?: ReactNode; type?: string }) =>
    createElement('span', { 'data-type': type }, children)
  const Space = ({ children }: { children?: ReactNode }) =>
    createElement('div', null, children)
  return {
    App: { useApp: () => ui },
    Button,
    Card: ({ children }: { children?: ReactNode }) =>
      createElement('div', null, children),
    Col: ({ children }: { children?: ReactNode }) =>
      createElement('div', null, children),
    Drawer: ({ open, title, children }: { open: boolean; title?: ReactNode; children?: ReactNode }) =>
      open ? createElement('div', null, title, children) : null,
    Input: {
      Search: ({ placeholder, onSearch }: { placeholder?: string; onSearch?: (v: string) => void }) =>
        createElement(
          'input',
          {
            placeholder,
            'data-testid': 'report-search',
            onKeyDown: (e: KeyboardEvent) => {
              if (e.key === 'Enter' && onSearch) onSearch('关键词')
            },
          },
        ),
    },
    Popconfirm: ({ children, onConfirm }: { children?: ReactNode; onConfirm?: () => void }) =>
      createElement(
        'span',
        { 'data-testid': 'popconfirm', onClick: onConfirm },
        children,
      ),
    Row: ({ children }: { children?: ReactNode }) =>
      createElement('div', null, children),
    Select: ({ placeholder, options, value, onChange }: {
      placeholder?: string
      options?: Array<{ value: string; label: string }>
      value?: string
      onChange?: (v: string) => void
    }) =>
      createElement('select', { 'data-placeholder': placeholder, value, onChange: () => onChange?.('noise') },
        (options || []).map((o) => createElement('option', { key: o.value, value: o.value }, o.label)),
      ),
    Space,
    Statistic: ({ title, value }: { title?: ReactNode; value?: ReactNode }) =>
      createElement('div', null, String(title), ':', String(value)),
    Table: ({
      dataSource,
      columns,
      locale,
      loading,
    }: {
      dataSource?: Array<Record<string, unknown>>
      columns?: Array<{
        key?: string
        dataIndex?: string
        render?: (v: unknown, row: Record<string, unknown>) => ReactNode
      }>
      locale?: { emptyText?: ReactNode }
      loading?: boolean
    }) =>
      createElement(
        'div',
        { 'data-loading': String(!!loading) },
        !dataSource || dataSource.length === 0
          ? locale?.emptyText ?? null
          : dataSource.map((row) =>
              createElement(
                'div',
                { key: String(row.id) },
                String(row.report_no ?? ''),
                (columns || []).map((col, i) =>
                  col.render
                    ? createElement(
                        'span',
                        { key: i },
                        col.render(row[col.dataIndex ?? ''], row),
                      )
                    : null,
                ),
              ),
            ),
      ),
    Tag: ({ children, color }: { children?: ReactNode; color?: string }) =>
      createElement('span', { 'data-color': color }, children),
    Tooltip: ({ children }: { children?: ReactNode }) => createElement('span', null, children),
    Typography: { Text },
  }
})

vi.mock('@ant-design/icons', () => ({
  DeleteOutlined: () => null,
  DownloadOutlined: () => null,
  EyeOutlined: () => null,
  FileAddOutlined: () => null,
  FundOutlined: () => null,
  RadiusSettingOutlined: () => null,
  WarningOutlined: () => null,
}))

import OhDetectionReportPanel from './OhDetectionReportPanel'
import type { OhDetectionReport } from '@/types/safety'

const REPORT: OhDetectionReport = {
  id: 'r-1',
  report_no: 'NZXZW-J-2026-141',
  report_name: '职业病危害因素检测报告',
  company_name: '丽珠集团（宁夏）制药有限公司',
  detection_agency: '宁夏智信安全技术检测有限公司',
  detection_date: '2026-09-10',
  table_count: 20,
  total_points: 416,
  exceed_points: 2,
  noise_post_points: 75,
  source_file_name: 'report.pdf',
  source_file_path: 'uploads/x.pdf',
  source_file_sha256: 'abc',
  parse_mode: 'rules',
  parse_warnings: null,
  remark: '',
  created_at: '2026-10-01T00:00:00Z',
  updated_at: '2026-10-01T00:00:00Z',
}

function okList() {
  return {
    code: 200,
    message: 'success',
    data: [REPORT],
    meta: {
      report_count: 1,
      total_points: 416,
      exceed_points: 2,
      noise_post_points: 75,
    },
  }
}

describe('OhDetectionReportPanel', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    vi.clearAllMocks()
    Object.assign(permState, { canOperate: true, canImport: true, canDelete: true })
    actions.getOhDetectionReports.mockResolvedValue(okList())
    actions.getOhDetectionResults.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [],
      meta: { total: 0 },
    })
    actions.deleteOhDetectionReport.mockResolvedValue({ code: 200, message: 'success' })
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
  })

  async function flushLoad() {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 5))
    })
  }

  function findButton(text: string): HTMLButtonElement {
    const matched = Array.from(container.querySelectorAll('button')).find((btn) =>
      btn.textContent?.includes(text),
    )
    if (!matched) {
      throw new Error(`button ${text} not found`)
    }
    return matched as HTMLButtonElement
  }

  it('渲染报告台账与聚合统计', async () => {
    await act(async () => {
      root.render(<OhDetectionReportPanel />)
    })
    await flushLoad()
    expect(container.textContent).toContain('NZXZW-J-2026-141')
    expect(container.textContent).toContain('报告数:1')
    expect(container.textContent).toContain('检测记录:416')
    expect(container.textContent).toContain('超标记录:2')
    expect(container.textContent).toContain('噪声作业岗位记录:75')
    expect(container.textContent).toContain('规则识别')
  })

  it('无操作或导入权限时导入按钮禁用', async () => {
    Object.assign(permState, { canOperate: false, canImport: false, canDelete: false })
    await act(async () => {
      root.render(<OhDetectionReportPanel />)
    })
    await flushLoad()
    expect(findButton('导入检测报告').disabled).toBe(true)
    expect(container.textContent).toContain('当前页面无操作权限')
  })

  it('加载失败时展示错误空态', async () => {
    actions.getOhDetectionReports.mockResolvedValue({
      code: 500,
      message: '后端不可用',
    })
    await act(async () => {
      root.render(<OhDetectionReportPanel />)
    })
    await flushLoad()
    expect(container.textContent).toContain('加载失败：后端不可用')
  })

  it('删除走确认并刷新列表', async () => {
    await act(async () => {
      root.render(<OhDetectionReportPanel />)
    })
    await flushLoad()
    const del = container.querySelector<HTMLButtonElement>(
      '[data-testid="popconfirm"] button',
    )
    expect(del).toBeTruthy()
    await act(async () => {
      del?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await flushLoad()
    expect(actions.deleteOhDetectionReport).toHaveBeenCalledWith('r-1')
    expect(actions.getOhDetectionReports).toHaveBeenCalledTimes(2)
  })

  it('点击报告编号打开明细抽屉并按筛选加载', async () => {
    actions.getOhDetectionResults.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [],
      meta: { total: 416 },
    })
    await act(async () => {
      root.render(<OhDetectionReportPanel />)
    })
    await flushLoad()
    await act(async () => {
      findButton('NZXZW-J-2026-141').click()
    })
    await flushLoad()
    expect(container.textContent).toContain('检测明细 — NZXZW-J-2026-141')
    expect(actions.getOhDetectionResults).toHaveBeenCalledWith(
      'r-1',
      expect.objectContaining({ page: 1, page_size: 20 }),
    )
    // 触发危害因素筛选：Select stub onChange 固定派发 noise
    const select = container.querySelector('select')
    await act(async () => {
      select?.dispatchEvent(new Event('change', { bubbles: true }))
    })
    await flushLoad()
    expect(actions.getOhDetectionResults).toHaveBeenLastCalledWith(
      'r-1',
      expect.objectContaining({ factor_category: 'noise' }),
    )
  })
})
