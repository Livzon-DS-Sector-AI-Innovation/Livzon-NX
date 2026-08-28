/* @vitest-environment happy-dom */
/* eslint-disable @typescript-eslint/no-explicit-any */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const actions = vi.hoisted(() => ({
  importPurchaseRequestTable: vi.fn(),
}))

const ui = vi.hoisted(() => ({
  message: { error: vi.fn(), success: vi.fn() },
}))

vi.mock('@/actions/purchasing', () => actions)

const uploadProps: Array<Record<string, any>> = []

vi.mock('antd', async () => {
  const React = await import('react')
  const App = { useApp: () => ({ message: ui.message }) }
  const Upload = ({ children, ...props }: Record<string, any>) => {
    uploadProps.push(props)
    return React.createElement('div', { 'data-testid': 'upload' }, children)
  }
  const Modal = ({ open, onCancel, children }: Record<string, any>) =>
    open
      ? React.createElement(
          'div',
          null,
          children,
          React.createElement('button', { onClick: onCancel }, '关闭')
        )
      : null
  const Button = ({ children, onClick }: Record<string, any>) =>
    React.createElement('button', { onClick }, children)
  const Alert = ({ message, description }: Record<string, any>) =>
    React.createElement(
      'div',
      null,
      String(message),
      description ? `：${String(description)}` : ''
    )
  const Table = ({ columns = [], dataSource, rowKey }: Record<string, any>) =>
    React.createElement(
      'div',
      null,
      `table-rows:${(dataSource ?? []).length}`,
      ...(dataSource ?? []).map((row: Record<string, any>, index: number) =>
        React.createElement(
          'div',
          {
            key:
              typeof rowKey === 'function'
                ? String(rowKey(row, index))
                : typeof rowKey === 'string'
                  ? String(row[rowKey])
                  : index,
          },
          ...columns.map((column: Record<string, any>) =>
            React.createElement(
              'span',
              { key: String(column.key ?? column.dataIndex ?? index) },
              typeof column.render === 'function'
                ? column.render(
                    column.dataIndex ? row[column.dataIndex] : undefined,
                    row,
                    index
                  )
                : String(row[column.dataIndex] ?? '')
            )
          )
        )
      )
    )
  const Typography = { Title: ({ children }: Record<string, any>) => React.createElement('div', null, children) }
  const Space = ({ children }: Record<string, any>) => React.createElement('div', null, children)
  return { App, Upload, Modal, Button, Alert, Table, Typography, Space }
})

vi.mock('@ant-design/icons', () => ({
  UploadOutlined: () => null,
}))

import { PurchaseRequestImportButton } from './PurchaseRequestImportButton'

function importResult(overrides: Record<string, any> = {}) {
  return {
    code: 200,
    message: 'success',
    data: {
      file_name: '采购申请.xlsx',
      total_sheets: 2,
      imported_requests: [
        {
          request_id: 'r1',
          sheet_name: '五金材料',
          category: 'hardware',
          category_label: '五金材料',
          category_source: 'inferred',
          request_department: '102一车间',
          request_date: '2026-08-14',
          items_count: 2,
        },
      ],
      failed_rows: [
        { sheet_name: '电气', row: 3, message: '第3行数量无效' },
      ],
      ...overrides,
    },
  }
}

describe('PurchaseRequestImportButton', () => {
  let root: Root
  let container: HTMLElement

  beforeEach(() => {
    vi.clearAllMocks()
    uploadProps.length = 0
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
  })

  it('uploads a table file and renders the import result', async () => {
    actions.importPurchaseRequestTable.mockResolvedValue(importResult())
    const onImported = vi.fn()

    act(() => {
      root.render(<PurchaseRequestImportButton onImported={onImported} />)
    })

    const file = new File(['xlsx-bytes'], '采购申请.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    const onSuccess = vi.fn()
    await act(async () => {
      await uploadProps[0].customRequest({ file, onSuccess })
    })

    expect(actions.importPurchaseRequestTable).toHaveBeenCalledTimes(1)
    const formData = actions.importPurchaseRequestTable.mock.calls[0][0] as FormData
    expect(formData.get('file')).toBe(file)
    expect(onSuccess).toHaveBeenCalled()
    expect(onImported).toHaveBeenCalled()

    expect(container.textContent).toContain('成功导入 1 份采购申请草稿，共 2 条明细')
    expect(container.textContent).toContain('五金材料（按字段推断）')
    expect(container.textContent).toContain('失败明细（1 条）')
    expect(container.textContent).toContain('第3行数量无效')
  })

  it('rejects unsupported file extensions before uploading', async () => {
    act(() => {
      root.render(<PurchaseRequestImportButton />)
    })

    const file = new File(['docx-bytes'], '采购申请.docx', { type: 'application/octet-stream' })
    await act(async () => {
      await uploadProps[0].customRequest({ file, onSuccess: vi.fn() })
    })

    expect(actions.importPurchaseRequestTable).not.toHaveBeenCalled()
    expect(ui.message.error).toHaveBeenCalledWith('请上传 xlsx、xls 或 csv 格式的表格文件')
  })

  it('surfaces the backend error message when the import fails', async () => {
    actions.importPurchaseRequestTable.mockResolvedValue({
      code: 400,
      message: '上传文件为空',
      data: null,
    })

    act(() => {
      root.render(<PurchaseRequestImportButton />)
    })

    const file = new File([''], '采购申请.xlsx', { type: 'application/octet-stream' })
    await act(async () => {
      await uploadProps[0].customRequest({ file, onSuccess: vi.fn() })
    })

    expect(ui.message.error).toHaveBeenCalledWith('上传文件为空')
  })

  it('shows a warning when no request was imported', async () => {
    actions.importPurchaseRequestTable.mockResolvedValue(
      importResult({
        imported_requests: [],
        failed_rows: [{ sheet_name: 'Sheet1', row: null, message: '无法识别采购类型' }],
      })
    )

    act(() => {
      root.render(<PurchaseRequestImportButton />)
    })

    const file = new File(['csv-bytes'], '申请.csv', { type: 'text/csv' })
    await act(async () => {
      await uploadProps[0].customRequest({ file, onSuccess: vi.fn() })
    })

    expect(container.textContent).toContain('没有成功导入任何采购申请')
    expect(container.textContent).toContain('无法识别采购类型')
  })

  it('surfaces unexpected import failures', async () => {
    actions.importPurchaseRequestTable.mockRejectedValue(new Error('network'))

    act(() => {
      root.render(<PurchaseRequestImportButton />)
    })

    const file = new File(['xlsx-bytes'], '采购申请.xlsx', { type: 'application/octet-stream' })
    await act(async () => {
      await uploadProps[0].customRequest({ file, onSuccess: vi.fn() })
    })

    expect(ui.message.error).toHaveBeenCalledWith('采购申请导入失败，请稍后重试')
  })

  it('closes the result modal with the confirm button', async () => {
    actions.importPurchaseRequestTable.mockResolvedValue(importResult())

    act(() => {
      root.render(<PurchaseRequestImportButton />)
    })

    const file = new File(['xlsx-bytes'], '采购申请.xlsx', { type: 'application/octet-stream' })
    await act(async () => {
      await uploadProps[0].customRequest({ file, onSuccess: vi.fn() })
    })
    expect(container.textContent).toContain('成功导入 1 份采购申请草稿')

    await act(async () => {
      const confirmButton = Array.from(container.querySelectorAll('button')).find(
        (button) => button.textContent === '知道了',
      )
      confirmButton?.click()
    })

    expect(container.textContent).not.toContain('成功导入 1 份采购申请草稿')
  })
})
