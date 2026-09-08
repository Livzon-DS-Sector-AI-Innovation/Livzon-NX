/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const actions = vi.hoisted(() => ({
  uploadScheduleExcel: vi.fn(),
  getScheduleExcelArchives: vi.fn(),
  getScheduleExcelArchive: vi.fn(),
  deleteScheduleExcelArchive: vi.fn(),
}))

vi.mock('@/actions/production', () => actions)

// Mock antd Upload so tests can drive beforeUpload deterministically.
const fakeUpload = vi.hoisted(() => ({
  trigger: null as null | ((file: unknown) => unknown),
}))

vi.mock('antd', async () => {
  const React = await import('react')
  const actual = await vi.importActual<typeof import('antd')>('antd')
  const Upload = (props: Record<string, unknown>) =>
    React.createElement(
      'div',
      { className: 'ant-upload' },
      props.children as React.ReactNode,
    )
  Upload.displayName = 'Upload'
  const UploadDragger = (props: Record<string, unknown>) => {
    fakeUpload.trigger = (file: unknown) =>
      (props.beforeUpload as (f: unknown) => unknown)?.(file)
    return React.createElement(
      'button',
      { type: 'button', className: 'ant-upload ant-upload-drag' },
      props.children as React.ReactNode,
    )
  }
  UploadDragger.displayName = 'Upload.Dragger'
  Upload.Dragger = UploadDragger
  return { ...actual, Upload }
})

import SchedulingPage from './page'

const ARCHIVE_SUMMARY = [
  {
    id: 'a-1',
    file_name: '2026-09排产.xlsx',
    sheet_name: '排产快照',
    row_count: 301,
    col_count: 5,
    created_by_name: '张工',
    created_at: '2026-09-08T02:00:00+08:00',
  },
]

const UPLOAD_RESULT = {
  code: 200,
  message: 'success',
  data: {
    id: 'a-2',
    file_name: '9月排产.xlsx',
    sheet_name: '9月排产',
    rows: [['排产计划 2026年7月1日 至 7月15日', '备注'], ['5', 'x']],
    merges: [{ s: { r: 0, c: 0 }, e: { r: 0, c: 1 } }],
    col_widths: [120, 80],
    row_count: 2,
    col_count: 2,
    created_at: '2026-09-08T02:00:00+08:00',
  },
}

describe('SchedulingPage archive flow', () => {
  let root: Root
  let container: HTMLElement

  beforeEach(() => {
    actions.getScheduleExcelArchives.mockResolvedValue({
      code: 200,
      message: 'success',
      data: ARCHIVE_SUMMARY,
    })
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  async function render() {
    act(() => {
      root.render(<App><SchedulingPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
  }

  it('loads and renders the archive history list', async () => {
    await render()
    expect(actions.getScheduleExcelArchives).toHaveBeenCalled()
    const text = container.textContent || ''
    expect(text).toContain('排产计划')
    expect(text).toContain('历史存档')
    expect(text).toContain('2026-09排产.xlsx')
    expect(text).toContain('301 行 × 5 列')
    expect(text).toContain('张工')
    expect(text).toContain('不设行数上限')
  })

  it('shows the empty state when there are no archives', async () => {
    actions.getScheduleExcelArchives.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [],
    })
    await render()
    const text = container.textContent || ''
    expect(text).toContain('暂无存档')
  })

  it('uploads a file to the backend and renders the archived table', async () => {
    actions.uploadScheduleExcel.mockResolvedValue(UPLOAD_RESULT)
    await render()

    const file = new File(['fake'], '9月排产.xlsx')
    await act(async () => {
      fakeUpload.trigger?.(file)
      await new Promise((r) => setTimeout(r, 60))
    })

    expect(actions.uploadScheduleExcel).toHaveBeenCalledTimes(1)
    const formData = actions.uploadScheduleExcel.mock.calls[0][0] as FormData
    expect(formData.get('file')).toBe(file)

    const text = (container.textContent || '') + (document.body.textContent || '')
    // message 提示渲染在 body portal
    expect(text).toContain('已存档：9月排产.xlsx')
    // 后端返回的行数据渲染成表格
    expect(text).toContain('排产计划 2026年7月1日 至 7月15日')
    expect(text).toContain('5')
    // 列表刷新
    expect(actions.getScheduleExcelArchives).toHaveBeenCalledTimes(2)
  })

  it('shows an error message when the upload action fails', async () => {
    actions.uploadScheduleExcel.mockResolvedValue({
      code: 400,
      message: 'Excel 解析失败：bad',
      data: null,
    })
    await render()

    const file = new File(['fake'], 'broken.xlsx')
    await act(async () => {
      fakeUpload.trigger?.(file)
      await new Promise((r) => setTimeout(r, 60))
    })
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('Excel 解析失败：bad')
  })
})
