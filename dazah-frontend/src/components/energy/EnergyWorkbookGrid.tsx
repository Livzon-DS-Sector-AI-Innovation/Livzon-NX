import { useRef, useState, type ComponentProps, type KeyboardEvent, type MouseEvent } from 'react'
import { Space, Table, Tag, Typography } from 'antd'
import type { ReactNode } from 'react'
import { formatAmount, type WorkbookReport } from '@/lib/api/energy-ledger'
import { reviewDetails, sourceComparisonDetails } from './energy-review'
import styles from './EnergyWorkbookGrid.module.css'
import { readableWorkbookNumber, sourceCalculationText, workbookCellText, type WorkbookSort } from './workbook-view'

type Position = { row: number; column: number }
type Selection = { start: Position; end: Position }
type Cell = WorkbookReport['rows'][number]['cells'][string]

function WorkbookTable(props: ComponentProps<'table'>) {
  return <table {...props} role="grid" aria-label="能源报表数据" />
}

function renderCell(cell: Cell | undefined) {
  if (!cell || ['complete', 'adjusted', 'source_blank'].includes(cell.status)) return readableWorkbookNumber(workbookCellText(cell))
  if (cell.status === 'not_applicable') return <Typography.Text type="secondary">不适用</Typography.Text>
  if (cell.status !== 'pending_review') return <Tag color="warning">{workbookCellText(cell)}</Tag>
  const reviews = reviewDetails(cell.provenance)
  const comparison = sourceComparisonDetails(cell.provenance)
  if (comparison) return <Space orientation="vertical" size={0}><Typography.Text>{readableWorkbookNumber(formatAmount(comparison.reportedValue))}</Typography.Text><Tag color="warning">待核对</Tag><Typography.Text>系统计算值：{sourceCalculationText(cell)}</Typography.Text><Typography.Text>差异（原表－系统）：{comparison.difference === null ? '无法计算' : readableWorkbookNumber(formatAmount(comparison.difference))}</Typography.Text><Typography.Text type="secondary">{comparison.source}；{[...new Set(reviews.map(review => review.reason))].join('；')}</Typography.Text></Space>
  return <Space orientation="vertical" size={0}><Tag color="warning">待确认</Tag><Typography.Text>原表值：{reviews.map(review => formatAmount(review.reportedValue)).join('；') || '—'}</Typography.Text><Typography.Text>系统计算值：{formatAmount(cell.calculated_value)}</Typography.Text><Typography.Text type="secondary">{reviews.map(review => `${review.reason}；${review.source}`).join('；')}</Typography.Text></Space>
}

export type WorkbookEditing = { canEdit: (date: string, key: string) => boolean; start: (date: string, key: string) => void; render: (date: string, key: string) => ReactNode }

export function EnergyWorkbookGrid({ report, loading, density = 'middle', sort, onSort, editing }: { report?: WorkbookReport; loading: boolean; density?: 'middle' | 'small'; sort?: WorkbookSort; onSort?: (sort: WorkbookSort) => void; editing?: WorkbookEditing }) {
  const container = useRef<HTMLDivElement>(null)
  const [selection, setSelection] = useState<Selection>({ start: { row: 0, column: 0 }, end: { row: 0, column: 0 } })
  const rows = report?.rows ?? []
  const columns = report?.columns ?? []
  const top = Math.min(selection.start.row, selection.end.row)
  const bottom = Math.max(selection.start.row, selection.end.row)
  const left = Math.min(selection.start.column, selection.end.column)
  const right = Math.max(selection.start.column, selection.end.column)

  function move(position: Position, extend = false) {
    setSelection(current => ({ start: extend ? current.start : position, end: position }))
    const target = container.current?.querySelector<HTMLElement>(`[data-grid-row="${position.row}"][data-grid-column="${position.column}"]`)
    target?.focus({ preventScroll: true })
    target?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' })
  }

  function navigate(event: KeyboardEvent<HTMLElement>, position: Position) {
    if (event.target !== event.currentTarget) return
    if (event.key === 'F2' && editable(position.row, position.column)) {
      event.preventDefault(); editing?.start(rows[position.row].date, columns[position.column - 1].key); return
    }
    const { key, ctrlKey, metaKey, shiftKey } = event
    if ((ctrlKey || metaKey) && key.toLowerCase() === 'a') {
      event.preventDefault()
      setSelection({ start: { row: 0, column: 0 }, end: { row: rows.length - 1, column: columns.length } })
      return
    }
    let { row, column } = position
    switch (key) {
      case 'ArrowUp': row = ctrlKey || metaKey ? 0 : row - 1; break
      case 'ArrowDown': row = ctrlKey || metaKey ? rows.length - 1 : row + 1; break
      case 'ArrowLeft': column = ctrlKey || metaKey ? 0 : column - 1; break
      case 'ArrowRight': column = ctrlKey || metaKey ? columns.length : column + 1; break
      case 'Home': column = 0; if (ctrlKey || metaKey) row = 0; break
      case 'End': column = columns.length; if (ctrlKey || metaKey) row = rows.length - 1; break
      case 'Enter': row += shiftKey ? -1 : 1; break
      case 'Tab':
        column += shiftKey ? -1 : 1
        if (column < 0) { row--; column = columns.length }
        if (column > columns.length) { row++; column = 0 }
        if (row < 0 || row >= rows.length) return
        break
      case 'Escape': move(position); return
      default: return
    }
    event.preventDefault()
    move({ row: Math.max(0, Math.min(rows.length - 1, row)), column: Math.max(0, Math.min(columns.length, column)) }, shiftKey && key !== 'Tab' && key !== 'Enter')
  }

  function editable(row: number, column: number) {
    return !loading && column > 0 && Boolean(editing?.canEdit(rows[row].date, columns[column - 1].key))
  }
  function cellProps(row: number, column: number) {
    const selected = row >= top && row <= bottom && column >= left && column <= right
    return {
      'data-grid-row': row, 'data-grid-column': column,
      'aria-selected': selected,
      role: 'gridcell',
      'aria-readonly': !editable(row, column),
      title: editable(row, column) ? '双击或按 F2 填写与修改' : undefined,
      onDoubleClick: () => { if (editable(row, column)) editing?.start(rows[row].date, columns[column - 1].key) },
      tabIndex: row === selection.end.row && column === selection.end.column ? 0 : -1,
      className: selected ? styles.selected : undefined,
      onMouseDown: (event: MouseEvent<HTMLElement>) => {
        if (event.target instanceof Element && event.target.closest('input, button, .ant-input-number')) return
        if (event.button !== 0) return
        event.preventDefault()
        move({ row, column }, event.shiftKey)
      },
      onMouseEnter: (event: MouseEvent<HTMLElement>) => {
        if (event.buttons === 1) move({ row, column }, true)
      },
      onKeyDown: (event: KeyboardEvent<HTMLElement>) => navigate(event, { row, column }),
    }
  }

  return <div ref={container} className={styles.grid} role="group" aria-label={`${report?.dataset ?? '能源'}数据表`} onCopy={event => {
    if (event.target instanceof HTMLInputElement) return
    if (!rows.length) return
    const text = rows.slice(top, bottom + 1).map(row => [row.date, ...columns.map(column => workbookCellText(row.cells[column.key]))]
      .slice(left, right + 1).map(value => value.replace(/[\t\r\n]+/g, ' ')).join('\t')).join('\n')
    event.preventDefault()
    event.clipboardData.setData('text/plain', text)
  }}>
    <Table rowKey="date" size={density} components={{ table: WorkbookTable }} loading={loading} dataSource={rows} pagination={false} scroll={{ x: columns.length * 160 + 128 }} onChange={(_, __, sorter) => {
      if (Array.isArray(sorter)) return
      onSort?.(sorter.order && sorter.columnKey ? { key: String(sorter.columnKey), order: sorter.order } : undefined)
    }} columns={[
      { title: '日期', key: 'date', dataIndex: 'date', width: 128, fixed: 'left', sorter: Boolean(onSort), sortOrder: sort?.key === 'date' ? sort.order : null, onCell: (_, row) => cellProps(row ?? 0, 0) },
      ...columns.map((column, index) => ({ title: <span className={styles.columnHeading}><span>{column.label}</span>{column.unit && !['待确认', '原表数值单位', '比例'].includes(column.unit) && <small>{column.unit}</small>}</span>, key: column.key, width: 160, sorter: Boolean(onSort), sortOrder: sort?.key === column.key ? sort.order : null, align: 'right' as const, onCell: (_: WorkbookReport['rows'][number], row?: number) => cellProps(row ?? 0, index + 1), render: (_: unknown, row: WorkbookReport['rows'][number]) => editing?.render(row.date, column.key) ?? renderCell(row.cells[column.key]) })),
    ]} />
  </div>
}
