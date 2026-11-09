import { formatAmount, QUALITY_LABELS, type WorkbookCell, type WorkbookReport } from '@/lib/api/energy-ledger'
import { reviewDetails, sourceComparisonDetails } from './energy-review'

export type WorkbookRow = WorkbookReport['rows'][number]
export type WorkbookSort = { key: string; order: 'ascend' | 'descend' } | undefined

export function workbookCellText(cell: WorkbookCell | undefined): string {
  if (!cell) return '—'
  if (cell.status === 'not_applicable') return '不适用'
  if (cell.status === 'pending_review') {
    const comparison = sourceComparisonDetails(cell.provenance)
    if (comparison) return `待核对；原表值：${formatAmount(comparison.reportedValue)}；系统计算值：${sourceCalculationText(cell)}；差异（原表－系统）：${comparison.difference === null ? '无法计算' : formatAmount(comparison.difference)}`
    const reviews = reviewDetails(cell.provenance)
    return `待确认；原表值：${reviews.map(review => formatAmount(review.reportedValue)).join('；') || '—'}；系统计算值：${formatAmount(cell.calculated_value)}`
  }
  return ['complete', 'adjusted', 'source_blank'].includes(cell.status)
    ? formatAmount(cell.value) : QUALITY_LABELS[cell.status] || cell.status
}

export function sourceCalculationText(cell: WorkbookCell): string {
  if (cell.calculated_value != null) return formatAmount(cell.calculated_value)
  const comparison = sourceComparisonDetails(cell.provenance)
  const status = comparison?.calculationStatus ?? ''
  return `无法重算（${QUALITY_LABELS[status] || status || '来源待核对'}）`
}

export function readableWorkbookNumber(value: string): string {
  if (!/^[+-]?\d+(?:\.\d+)?$/.test(value)) return value
  const [integer, fraction] = value.split('.')
  return integer.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + (fraction ? `.${fraction}` : '')
}

export function needsWorkbookAttention(cell: WorkbookCell | undefined): boolean {
  return !cell || !['complete', 'adjusted', 'source_blank', 'not_applicable'].includes(cell.status)
}

function decimalParts(value: string) {
  const match = /^([+-]?)(\d+)(?:\.(\d+))?(?:[eE]([+-]?\d+))?$/.exec(value)
  if (!match) return undefined
  const exponent = Number(match[4] ?? 0)
  // Energy quantities are bounded decimals; reject unbounded external exponents.
  if (!Number.isSafeInteger(exponent) || Math.abs(exponent) > 100) return undefined
  const fraction = match[3] ?? ''
  return { coefficient: BigInt(`${match[1]}${match[2]}${fraction}`), scale: fraction.length - exponent }
}

export function sortWorkbookRows(rows: WorkbookRow[], sort: WorkbookSort): WorkbookRow[] {
  if (!sort) return rows
  return [...rows].sort((a, b) => {
    if (sort.key === 'date') return a.date.localeCompare(b.date) * (sort.order === 'ascend' ? 1 : -1)
    const first = workbookCellText(a.cells[sort.key]), second = workbookCellText(b.cells[sort.key])
    const firstNumeric = decimalParts(first), secondNumeric = decimalParts(second)
    if (Boolean(firstNumeric) !== Boolean(secondNumeric)) return firstNumeric ? -1 : 1
    if (!firstNumeric || !secondNumeric) return a.date.localeCompare(b.date)
    const scale = Math.max(firstNumeric.scale, secondNumeric.scale)
    const firstFixed = firstNumeric.coefficient * BigInt(10) ** BigInt(scale - firstNumeric.scale)
    const secondFixed = secondNumeric.coefficient * BigInt(10) ** BigInt(scale - secondNumeric.scale)
    return (firstFixed < secondFixed ? -1 : firstFixed > secondFixed ? 1 : 0) * (sort.order === 'ascend' ? 1 : -1)
  })
}

export function workbookClipboardText(rows: WorkbookRow[], columns: WorkbookReport['columns']): string {
  const clean = (value: string) => value.replace(/[\t\r\n]+/g, ' ')
  return [['日期', ...columns.map(column => column.label)], ...rows.map(row => [row.date, ...columns.map(column => workbookCellText(row.cells[column.key]))])]
    .map(row => row.map(clean).join('\t')).join('\n')
}
