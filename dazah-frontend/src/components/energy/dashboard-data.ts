import type { EChartsOption } from 'echarts'
import type { Report, WorkbookDataset, WorkbookReport } from '@/lib/api/energy-ledger'
import { reviewDetails } from './energy-review'

export const DASHBOARD_GROUPS = [
  { key: 'plant', label: '日总量', description: '全厂汇总口径；不与分类用量或车间用量再次相加。' },
  { key: 'usage', label: '分类用量', description: '五类能源用量来自原始表码差及固定计算关系，供日总量和车间台账引用。' },
  { key: 'workshop', label: '车间台账', description: '九张车间表按能源和温度分别统计；各能源不直接相加或计算能源结构占比。' },
  { key: 'source', label: '原始数据', description: '五类累计表码用于计算次日减当日的用量；电量同时包含原始字段及计算字段。表码不累计、不计算用量占比。' },
] as const
export type DashboardGroup = typeof DASHBOARD_GROUPS[number]['key']
export const QUANTITY_LABELS: Record<string, string> = { volume: '体积', heat: '热量', mass: '质量', electricity: '电量', ratio: '占比' }
export function datasetGroup(dataset: WorkbookDataset): DashboardGroup {
  if (dataset.name === '日总量') return 'plant'
  if (dataset.name.includes('车间')) return 'workshop'
  return dataset.kind === 'usage' ? 'usage' : 'source'
}

export function workbookMetric(report: WorkbookReport, columnKey: string) {
  const column = report.columns.find(item => item.key === columnKey)
  const points = report.rows.map(row => {
    const cell = row.cells[columnKey]
    const valid = Boolean(cell && ['complete', 'adjusted'].includes(cell.status) && cell.value !== null && Number.isFinite(Number(cell.value)))
    return { date: row.date, value: valid ? Number(cell.value) : null, raw: cell?.value ?? null, calculated: cell?.calculated_value ?? null, reviews: reviewDetails(cell?.provenance), status: cell?.status ?? 'missing_reading' }
  })
  const days = new Date(report.year, report.month, 0).getDate()
  const prefix = `${report.year}-${String(report.month).padStart(2, '0')}-`
  const complete = points.length === days && points.every((point, index) => point.value !== null && point.date === `${prefix}${String(index + 1).padStart(2, '0')}`)
  // A share is a partition of ONE measure over disjoint dates, never a sum of
  // source / subtotal / total columns or different energies and temperatures.
  const reading = column?.value_kind === 'reading' && report.dataset !== '电量'
  const additive = column && !reading && !['ratio', 'temperature', ''].includes(column.quantity_kind) && !/占比|比例|差值|差额|排空/.test(column.label) && !['%', '％', '比例'].includes(column.unit)
  const total = points.reduce((sum, point) => sum + (point.value ?? 0), 0)
  const shares = additive && complete && total > 0 && points.every(point => point.value !== null && point.value >= 0)
    ? points.map(point => ({ name: point.date, value: point.value! })) : []
  return { column, points, shares, complete, reading }
}

export function trendOption(name: string, unit: string, points: { date: string; value: number | null }[], reading = false): EChartsOption {
  return {
    aria: { enabled: true }, tooltip: { trigger: 'axis' }, legend: { type: 'scroll', bottom: 0 },
    grid: { left: 65, right: 24, top: 45, bottom: 65 },
    xAxis: { type: 'category', data: points.map(point => point.date.slice(5)), name: '日期' },
    yAxis: { type: 'value', name: unit, scale: reading },
    series: [{ name, type: 'line', connectNulls: false, showSymbol: true, data: points.map(point => point.value) }],
  }
}
export function shareOption(name: string, data: { name: string; value: number }[]): EChartsOption {
  return {
    aria: { enabled: true }, tooltip: { trigger: 'item', valueFormatter: value => String(value) },
    legend: { type: 'scroll', bottom: 0 },
    series: [{ name, type: 'pie', radius: ['38%', '62%'], center: ['50%', '43%'], label: { show: false }, emphasis: { label: { show: true, formatter: '{b}: {d}%' } }, data }],
  }
}

export function contributionOption(name: string, data: { name: string; value: number }[]): EChartsOption {
  const total = data.reduce((sum, item) => sum + item.value, 0)
  return {
    aria: { enabled: true }, tooltip: { trigger: 'axis', valueFormatter: value => `${value}%` }, legend: { bottom: 0 },
    grid: { left: 55, right: 24, top: 45, bottom: 65 },
    xAxis: { type: 'category', data: data.map(item => item.name.slice(5)), name: '日期' },
    yAxis: { type: 'value', name: '%' },
    series: [{ name, type: 'bar', data: data.map(item => Number((item.value / total * 100).toFixed(2))) }],
  }
}

export function workshopGroups(report: Report) {
  const groups = new Map<string, { label: string; unit: string; rows: NonNullable<Report['distribution']>; shares: { name: string; value: number }[] }>()
  for (const row of report.distribution ?? []) {
    if (row.quantity_kind === 'ratio') continue
    const key = JSON.stringify([row.category, row.unit, row.quantity_kind, row.temperature])
    const group = groups.get(key) ?? { label: `${row.category} ${row.temperature} · ${row.quantity_kind}`, unit: row.unit, rows: [], shares: [] }
    group.rows.push(row)
    groups.set(key, group)
  }
  for (const group of groups.values()) {
    if (group.rows.length && group.rows.every(row => row.expected_count > 0 && row.available_count === row.expected_count && row.value !== null && Number.isFinite(Number(row.value)) && Number(row.value) >= 0) && group.rows.some(row => Number(row.value) > 0)) {
      group.shares = group.rows.map(row => ({ name: row.workshop || '公共区域', value: Number(row.value) }))
    }
  }
  return groups
}
