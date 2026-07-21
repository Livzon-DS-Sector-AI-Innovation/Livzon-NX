'use client'

import type { CSSProperties, MouseEvent as ReactMouseEvent, ReactNode, ThHTMLAttributes } from 'react'
import type { TableColumnsType } from 'antd'

type ColumnWithDataIndex = {
  dataIndex?: string | number | readonly (string | number)[]
}

type HeaderCellProps = ThHTMLAttributes<HTMLTableCellElement> & {
  children?: ReactNode
  width?: number
  minWidth?: number
  resizable?: boolean
  onResizeStart?: (event: ReactMouseEvent<HTMLDivElement>) => void
}

export function ResizableHeaderCell({
  children,
  width,
  minWidth,
  resizable,
  onResizeStart,
  style,
  ...restProps
}: HeaderCellProps) {
  const mergedStyle: CSSProperties = {
    ...style,
    width,
    minWidth,
    position: 'relative',
  }

  return (
    <th {...restProps} style={mergedStyle}>
      <div style={{ paddingRight: resizable ? 14 : undefined }}>{children}</div>
      {resizable ? (
        <div
          onMouseDown={onResizeStart}
          style={{
            position: 'absolute',
            top: 0,
            right: -3,
            width: 8,
            height: '100%',
            cursor: 'col-resize',
            userSelect: 'none',
            zIndex: 2,
          }}
        />
      ) : null}
    </th>
  )
}

type ResizableOptions = {
  widths: Record<string, number>
  minWidths?: Record<string, number>
  onResizeStart: (columnKey: string, event: ReactMouseEvent<HTMLDivElement>) => void
}

export function buildResizableColumns<T extends object>(
  columns: TableColumnsType<T>,
  options: ResizableOptions,
): TableColumnsType<T> {
  const { widths, minWidths = {}, onResizeStart } = options
  const mapColumns = (inputColumns: TableColumnsType<T>): TableColumnsType<T> => inputColumns.map((column) => {
    const dataIndex = (column as ColumnWithDataIndex).dataIndex
    const normalizedDataIndex = Array.isArray(dataIndex) ? dataIndex.join('.') : dataIndex
    const columnKey = String(column.key ?? normalizedDataIndex ?? '')
    const width = columnKey ? widths[columnKey] ?? (typeof column.width === 'number' ? column.width : undefined) : column.width
    const minWidth = columnKey ? minWidths[columnKey] : undefined
    const canResize = Boolean(columnKey && width)
    const children = 'children' in column && Array.isArray(column.children)
      ? mapColumns(column.children as TableColumnsType<T>)
      : undefined

    return {
      ...column,
      ...(children ? { children } : {}),
      width,
      onHeaderCell: () => ({
        width,
        minWidth,
        resizable: canResize,
        onResizeStart: canResize
          ? (event: ReactMouseEvent<HTMLDivElement>) => onResizeStart(columnKey, event)
          : undefined,
      }),
    }
  })

  return mapColumns(columns)
}
