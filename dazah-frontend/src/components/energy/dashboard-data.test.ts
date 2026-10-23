import { expect, it } from 'vitest'
import type { Report, WorkbookReport } from '@/lib/api/energy-ledger'
import { contributionOption, datasetGroup, shareOption, trendOption, workbookMetric, workshopGroups } from './dashboard-data'

function workbook(overrides: Partial<WorkbookReport> = {}): WorkbookReport {
  return { year: 2026, month: 7, dataset: '饮用水量', available_count: 31, expected_count: 31,
    columns: [{ key: '2', label: '101用量', unit: 'm³', quantity_kind: 'volume', value_kind: 'usage' }],
    rows: Array.from({ length: 31 }, (_, index) => ({ date: `2026-07-${String(index + 1).padStart(2, '0')}`, cells: { '2': { value: index === 1 ? '20' : '0', status: 'complete' } } })), ...overrides }
}
it('classifies all four layers without adding source and downstream totals', () => {
  expect(datasetGroup({ name: '日总量', kind: 'usage' })).toBe('plant')
  expect(datasetGroup({ name: '101车间', kind: 'usage' })).toBe('workshop')
  expect(datasetGroup({ name: '饮用水量', kind: 'usage' })).toBe('usage')
  expect(datasetGroup({ name: '饮用水码', kind: 'reading' })).toBe('source')
  expect(datasetGroup({ name: '电量', kind: 'mixed' })).toBe('source')
})
it('preserves zero and partitions one usage metric by date', () => {
  const metric = workbookMetric(workbook(), '2')
  expect(metric.complete).toBe(true)
  expect(metric.shares).toHaveLength(31)
  expect(metric.shares.slice(0, 2)).toEqual([{ name: '2026-07-01', value: 0 }, { name: '2026-07-02', value: 20 }])
  expect(workbookMetric(workbook(), 'unknown').shares).toEqual([])
})
it('requires every calendar date and recognizes electricity inputs as daily energy rather than counters', () => {
  const data = workbook({ dataset: '电量' }); data.columns[0].value_kind = 'reading'
  expect(workbookMetric(data, '2').reading).toBe(false)
  expect(workbookMetric(data, '2').shares).toHaveLength(31)
  data.rows.pop()
  expect(workbookMetric(data, '2').shares).toEqual([])
})
it.each(['missing_reading', 'configuration_conflict', 'abnormal_usage', 'pending_review'])('keeps %s gaps and blocks incomplete shares', status => {
  const data = workbook(); data.rows[0].cells['2'] = { value: '9', status }
  const metric = workbookMetric(data, '2')
  expect(metric.points[0].value).toBeNull()
  expect(metric.points[0].raw).toBe('9')
  expect(metric.shares).toEqual([])
})
it('never calculates shares for raw counters, ratios, differences, negative, missing or zero-only values', () => {
  for (const patch of [{ value_kind: 'reading' as const }, { quantity_kind: 'ratio' }, { unit: '%' }, { label: '核对差额' }]) {
    const data = workbook(); Object.assign(data.columns[0], patch)
    expect(workbookMetric(data, '2').shares).toEqual([])
  }
  for (const value of ['-1', '0', null, 'Infinity']) {
    const data = workbook(); data.rows[1].cells['2'].value = value
    expect(workbookMetric(data, '2').shares).toEqual([])
  }
})
it('keeps workshop energy, unit, quantity and temperature scopes independent and blocks partial shares', () => {
  const row: NonNullable<Report['distribution']>[number] = { category: 'chilled_water', unit: 'm³', temperature: '7℃', quantity_kind: 'volume', workshop: '101车间', value: '20', available_count: 31, expected_count: 31 }
  const report: Report = { start_date: '2026-07-01', end_date: '2026-07-31', status: 'partial', rows: [], totals: [], total_count: 0, entry_total: 0, entry_completed: 0, distribution: [row, { ...row, workshop: '102车间', value: '30' }, { ...row, temperature: '-5℃' }, { ...row, unit: '万m³' }, { ...row, quantity_kind: 'heat' }, { ...row, category: 'air' }, { ...row, quantity_kind: 'ratio' }] }
  const groups = [...workshopGroups(report).values()]
  expect(groups).toHaveLength(5)
  expect(groups[0].shares.map(item => item.value)).toEqual([20, 30])
  report.distribution![0].available_count = 30
  expect([...workshopGroups(report).values()][0].shares).toEqual([])
})
it('produces accessible theme-neutral charts with dates, units, legends and explicit gaps', () => {
  const option = trendOption('101用量', 'm³', [{ date: '2026-07-01', value: 0 }, { date: '2026-07-02', value: null }])
  expect(option).toMatchObject({ aria: { enabled: true }, yAxis: { name: 'm³' }, series: [{ connectNulls: false, data: [0, null] }] })
  expect(shareOption('用量', [{ name: '101车间', value: 20 }])).toMatchObject({ aria: { enabled: true }, series: [{ type: 'pie', data: [{ name: '101车间', value: 20 }] }] })
  expect(contributionOption('每日占比', [{ name: '2026-07-01', value: 1 }, { name: '2026-07-02', value: 3 }])).toMatchObject({ yAxis: { name: '%' }, series: [{ type: 'bar', data: [25, 75] }] })
})

it('keeps reviewed original and calculated values while removing the date from trend and shares', () => {
  const data = workbook()
  data.rows[25].cells['2'] = { value: null, calculated_value: '2049315', status: 'pending_review', provenance: { review: [{ reason: '底码跳变与手填冲突', source: '飞书N31', reported_value: '28674' }] } }
  const metric = workbookMetric(data, '2')
  expect(metric.points[24].value).toBe(0)
  expect(metric.points[25]).toMatchObject({ value: null, raw: null, calculated: '2049315', status: 'pending_review', reviews: [{ reason: '底码跳变与手填冲突', source: '飞书N31', reportedValue: '28674' }] })
  expect(metric.points[26].value).toBe(0)
  expect(metric.shares).toEqual([])
})
