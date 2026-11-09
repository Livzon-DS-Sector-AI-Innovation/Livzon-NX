import { expect, it } from 'vitest'
import type { WorkbookReport } from '@/lib/api/energy-ledger'
import { displayMetric, monthlyOption, summarizeMetric, dashboardPeriods, workbookEvidence } from './dashboard-summary'

function report(month = 7): WorkbookReport {
  return { year: 2026, month, dataset: '日总量', available_count: 31, expected_count: 31,
    columns: [{ key: '6', label: '电日用量', unit: 'kWh', quantity_kind: 'electricity', value_kind: 'usage' }],
    rows: Array.from({ length: new Date(2026, month, 0).getDate() }, (_, index) => ({ date: `2026-${String(month).padStart(2, '0')}-${String(index + 1).padStart(2, '0')}`, cells: { '6': { value: index === 0 ? '0' : '10', status: 'complete' } } })),
  }
}

it('sums one measure, preserves zero and calculates averages using the actual calendar', () => {
  const data = report()
  data.rows.push({ date: '2026-06-30', cells: { '6': { value: '900', status: 'complete' } } })
  expect(summarizeMetric(data, '6')).toMatchObject({ total: 300, average: 300 / 31, available: 31, peak: { date: '2026-07-02', value: 10 } })
  expect(summarizeMetric(report(9), '6')).toMatchObject({ total: 290, average: 290 / 30, days: 30 })
  expect(displayMetric(0)).toBe('0')
  expect(displayMetric(null)).toBe('—')
})

it('builds a rolling comparison through year boundaries without fixing sample dates', () => {
  expect(dashboardPeriods(2028, 2)).toEqual([
    { year: 2027, month: 11 }, { year: 2027, month: 12 },
    { year: 2028, month: 1 }, { year: 2028, month: 2 },
  ])
})
it('shows field formulas and live reading revision evidence', () => {
  expect(workbookEvidence({ source_sheet: '电量', source_cell: 'B2', formula: '=SUM(C2:D2)' })).toBe('电量!B2；=SUM(C2:D2)')
  expect(workbookEvidence({ source_kind: 'reading', version: 3 })).toBe('填报版本 3')
  expect(workbookEvidence(undefined)).toBe('')
})
it.each([null, '', 'Infinity', '-1'])('excludes invalid %s and calculates totals and averages from valid days', value => {
  const data = report(); data.rows[1].cells['6'].value = value
  expect(summarizeMetric(data, '6')).toMatchObject({ total: 290, subtotal: 290, average: 290 / 30, available: 30, complete: false })
  expect(summarizeMetric(data, '6').points[1].raw).toBe(value)
})
it('rejects missing/duplicate dates, source errors and missing columns', () => {
  const data = report(); data.rows.push(data.rows[0])
  expect(summarizeMetric(data, '6')).toMatchObject({ total: 300, average: 10, available: 30 })
  data.rows.pop(); data.rows.pop()
  expect(summarizeMetric(data, '6').available).toBe(30)
  data.rows[0].cells['6'].status = 'source_formula_error'
  expect(summarizeMetric(data, '6').available).toBe(29)
  expect(summarizeMetric(data, 'unknown').available).toBe(0)
})
it('compares partial months while leaving unavailable and unit-mismatched months as gaps', () => {
  const changed = report(9); changed.columns[0].unit = '万kWh'
  const partial = report(10); partial.rows.pop()
  expect(monthlyOption('电量', 'kWh', [report(), undefined, changed, partial], '6', false, dashboardPeriods(2026, 10))).toMatchObject({ series: [{ data: [300, null, null, 290] }] })
  expect(monthlyOption('电量', 'kWh', [partial], '6', true, [{ year: 2026, month: 10 }])).toMatchObject({ series: [{ data: [290 / 30] }] })
  expect(monthlyOption('电量', 'kWh', [report()], '6', true, [{ year: 2026, month: 7 }])).toMatchObject({ yAxis: { name: 'kWh/日' }, series: [{ data: [300 / 31] }] })
  expect(monthlyOption('电量', '待确认', [report()], '6', false, dashboardPeriods(2026, 10))).toMatchObject({ yAxis: { name: '数值' } })
})

it('counts a single zero day as valid and leaves a month with no valid days empty', () => {
  const data = report(); data.rows = data.rows.slice(0, 1)
  expect(summarizeMetric(data, '6')).toMatchObject({ total: 0, average: 0, available: 1, complete: false })
  data.rows = []
  expect(summarizeMetric(data, '6')).toMatchObject({ total: null, average: null, available: 0 })
})

it('uses the 28 filled days rather than the 31 calendar days for an ongoing month', () => {
  const data = report(); data.rows = data.rows.slice(0, 28)
  expect(summarizeMetric(data, '6')).toMatchObject({ total: 270, average: 270 / 28, available: 28, days: 31 })
})
