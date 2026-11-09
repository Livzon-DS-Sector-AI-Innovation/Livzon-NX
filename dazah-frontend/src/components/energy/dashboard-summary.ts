import type { EChartsOption } from 'echarts'
import type { WorkbookReport } from '@/lib/api/energy-ledger'

export type DashboardPeriod = { year: number; month: number }
export function dashboardPeriods(year: number, month: number): DashboardPeriod[] {
  return [-3, -2, -1, 0].map(offset => {
    const date = new Date(year, month - 1 + offset, 1)
    return { year: date.getFullYear(), month: date.getMonth() + 1 }
  })
}
export const SUMMARY_METRICS = [
  { key: '6', label: '电量' }, { key: '7', label: '饮用水' },
  { key: '4', label: '蒸汽合计' }, { key: '8', label: '压缩空气' },
  { key: '9', label: '7℃冰水' }, { key: '10', label: '循环水' },
] as const

export function workbookEvidence(provenance: WorkbookReport['rows'][number]['cells'][string]['provenance']) {
  return [
    provenance?.source_sheet && provenance?.source_cell ? `${provenance.source_sheet}!${provenance.source_cell}` : '',
    typeof provenance?.formula === 'string' ? provenance.formula : '',
    provenance?.source_kind === 'reading' ? `填报版本 ${provenance.version ?? '—'}` : '',
  ].filter(Boolean).join('；')
}

export function summarizeMetric(report: WorkbookReport, key: string) {
  const column = report.columns.find(item => item.key === key)
  const days = new Date(report.year, report.month, 0).getDate()
  const points = Array.from({ length: days }, (_, index) => {
    const date = `${report.year}-${String(report.month).padStart(2, '0')}-${String(index + 1).padStart(2, '0')}`
    const matches = report.rows.filter(row => row.date === date)
    const cell = matches.length === 1 ? matches[0].cells[key] : undefined
    const numeric = cell?.value != null && String(cell.value).trim() !== '' ? Number(cell.value) : NaN
    const valid = Boolean(column && cell && ['complete', 'adjusted'].includes(cell.status) && Number.isFinite(numeric) && numeric >= 0)
    return { date, value: valid ? numeric : null, raw: cell?.value ?? null, status: cell && numeric < 0 ? 'abnormal_usage' : cell?.status ?? 'missing_reading', evidence: workbookEvidence(cell?.provenance) }
  })
  const available = points.filter(point => point.value !== null)
  const complete = available.length === days
  const subtotal = available.length ? available.reduce((sum, point) => sum + point.value!, 0) : null
  return { column, points, days, available: available.length, complete, subtotal,
    total: subtotal, average: subtotal !== null ? subtotal / available.length : null,
    peak: available.length ? available.reduce((best, point) => point.value! > best.value! ? point : best) : null }
}
export function displayMetric(value: number | null) {
  return value === null ? '—' : new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 }).format(value)
}
export function monthlyOption(label: string, unit: string, reports: (WorkbookReport | undefined)[], key: string, dailyAverage: boolean, periods: DashboardPeriod[]): EChartsOption {
  return {
    aria: { enabled: true }, tooltip: { trigger: 'axis' }, legend: { bottom: 0 },
    grid: { left: 72, right: 24, top: 40, bottom: 52 },
    xAxis: { type: 'category', data: periods.map(period => `${period.year}-${String(period.month).padStart(2, '0')}`) },
    yAxis: { type: 'value', name: unit === '待确认' ? '数值' : dailyAverage ? `${unit}/日` : unit },
    series: [{ name: `${label}${dailyAverage ? '日均' : '月累计'}`, type: 'bar', barMaxWidth: 44, data: reports.map(report => {
      if (!report) return null
      const metric = summarizeMetric(report, key)
      return metric.column?.unit === unit ? dailyAverage ? metric.average : metric.total : null
    }) }],
  }
}
