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

// 权限可控：历史修正入口按 production:schedule-archive 显隐
const permissionState = vi.hoisted(() => ({ codes: [] as string[] }))

vi.mock('@/hooks/usePermission', () => ({
  usePermission: () => ({
    has: (code: string) =>
      permissionState.codes.includes('*') || permissionState.codes.includes(code),
    hasAny: (codes: string[]) =>
      permissionState.codes.includes('*') ||
      codes.some((code) => permissionState.codes.includes(code)),
    permissions: permissionState.codes,
  }),
}))

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
    permissionState.codes = []
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

  const UPLOAD_WITH_HISTORY_CHANGES = {
    ...UPLOAD_RESULT,
    data: {
      ...UPLOAD_RESULT.data,
      merge: {
        recognized: true,
        matched_blocks: 1,
        frozen_columns: 4,
        discarded_changes: [
          {
            block: '2026-04',
            row: '发酵罐号',
            date: '2026-04-05',
            column: 1,
            old: 'B403',
            new: 'B404',
          },
        ],
        truncated: false,
        corrected: false,
        warning: '检测到 1 处「今天之前」的历史改动，已按冻结规则保留原存档',
      },
    },
  }

  it('freezes history changes without fix entry when lacking permission', async () => {
    permissionState.codes = []
    actions.uploadScheduleExcel.mockResolvedValue(UPLOAD_WITH_HISTORY_CHANGES)
    await render()

    const file = new File(['fake'], '9月排产.xlsx')
    await act(async () => {
      fakeUpload.trigger?.(file)
      await new Promise((r) => setTimeout(r, 60))
    })

    // 只上传一次；冻结告警对无权限用户仅提示联系管理员
    expect(actions.uploadScheduleExcel).toHaveBeenCalledTimes(1)
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('已按冻结规则保留原存档')
    expect(text).toContain('请联系管理员')
    expect(text).not.toContain('确认修正历史')
  })

  it('offers history fix with reason when permitted and re-uploads on confirm', async () => {
    permissionState.codes = ['production:schedule-archive']
    actions.uploadScheduleExcel
      .mockResolvedValueOnce(UPLOAD_WITH_HISTORY_CHANGES)
      .mockResolvedValueOnce({
        ...UPLOAD_RESULT,
        message: '排产 Excel 已存档，已按新文件修正历史 1 处',
      })
    await render()

    const file = new File(['fake'], '9月排产.xlsx')
    await act(async () => {
      fakeUpload.trigger?.(file)
      await new Promise((r) => setTimeout(r, 60))
    })

    // 差异确认弹窗出现：展示改动明细
    let text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('检测到「今天之前」的历史改动')
    expect(text).toContain('B403')
    expect(text).toContain('B404')

    // 原因为空时确认按钮禁用
    const okButton = [...document.querySelectorAll('button')].find((b) =>
      b.textContent?.includes('确认修正历史'),
    )
    expect(okButton).toBeDefined()
    expect((okButton as HTMLButtonElement).disabled).toBe(true)

    // 填写原因后确认 → 以 allow_history_fix 重传同一文件
    const textarea = document.body.querySelector('textarea')
    expect(textarea).not.toBeNull()
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(
        HTMLTextAreaElement.prototype,
        'value',
      )?.set
      setter?.call(textarea, '排产表笔误，实际进 B404')
      textarea?.dispatchEvent(new Event('input', { bubbles: true }))
      await new Promise((r) => setTimeout(r, 30))
    })
    await act(async () => {
      ;(
        [...document.querySelectorAll('button')].find((b) =>
          b.textContent?.includes('确认修正历史'),
        ) as HTMLButtonElement
      ).click()
      await new Promise((r) => setTimeout(r, 60))
    })

    expect(actions.uploadScheduleExcel).toHaveBeenCalledTimes(2)
    const fixCall = actions.uploadScheduleExcel.mock.calls[1]
    // allow_history_fix / history_fix_reason 由 action 实现追加到 FormData,
    // 页面测试 mock 了 action 模块,这里断言页面传递的选项与同一文件
    expect((fixCall[0] as FormData).get('file')).toBe(file)
    expect(fixCall[2]).toEqual({
      allowHistoryFix: true,
      historyFixReason: '排产表笔误，实际进 B404',
    })
    text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('已存档并按新文件修正历史')
  })

  it('shows history fix records entry from the archive list', async () => {
    actions.getScheduleExcelArchives.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [
        {
          ...ARCHIVE_SUMMARY[0],
          history_fixes: [
            {
              fixed_at: '2026-09-17T08:00:00+08:00',
              fixed_by_name: '张工',
              reason: '排产表笔误，实际进 B404',
              product_code: 'DR',
              file_name: '2026-09排产.xlsx',
              changes: [
                {
                  block: '2026-04',
                  row: '发酵罐号',
                  date: '2026-04-05',
                  column: 1,
                  old: 'B403',
                  new: 'B404',
                },
              ],
              changes_total: 1,
            },
          ],
        },
      ],
      meta: { page: 1, page_size: 50, total: 1, history_fix_total: 4 },
    })
    await render()

    // 列表行出现修正标记（不带数字：每份存档至多一条修正记录）
    let text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('历史修正')
    // 累计口径随 meta 返回，展示在历史存档卡片标题旁
    expect(text).toContain('本产品累计历史修正 4 次')

    // 点击行内"历史修正"标记 → 弹出修正记录（时间/操作人/原因 + 逐格改动）
    // （限定表格内并精确匹配,避免选中卡片标题的"累计历史修正"标签）
    const tag = [...container.querySelectorAll('table .ant-tag')].find(
      (el) => el.textContent?.trim() === '历史修正',
    )
    expect(tag).not.toBeUndefined()
    await act(async () => {
      ;(tag as HTMLElement).click()
      await new Promise((r) => setTimeout(r, 60))
    })
    text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('历史修正记录：2026-09排产.xlsx')
    expect(text).toContain('排产表笔误，实际进 B404')
    expect(text).toContain('发酵罐号')
    expect(text).toContain('B403')
    expect(text).toContain('B404')
  })
})
