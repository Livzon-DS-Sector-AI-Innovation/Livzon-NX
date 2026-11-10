import { expect, it } from 'vitest'
import { needsWorkbookAttention, readableWorkbookNumber, sortWorkbookRows, workbookCellText, workbookClipboardText, type WorkbookRow } from './workbook-view'

it('formats large decimal strings for reading without losing precision', () => {
  expect(readableWorkbookNumber('12345678901234567890.12345678')).toBe('12,345,678,901,234,567,890.12345678')
  expect(readableWorkbookNumber('-1234.05')).toBe('-1,234.05')
  expect(readableWorkbookNumber('0')).toBe('0')
  expect(readableWorkbookNumber('—')).toBe('—')
})

it('sorts decimal values exactly, keeps zero and negative values, and leaves gaps last', () => {
  const rows: WorkbookRow[] = ['9007199254740993.00000002', '9007199254740993.00000001', '0', '-0.00000001', null].map((value, index) => ({ date: `2026-07-0${index + 1}`, cells: { test: { value, status: value === null ? 'missing_reading' : 'complete' } } }))
  expect(sortWorkbookRows(rows, { key: 'test', order: 'ascend' }).map(row => row.date)).toEqual(['2026-07-04', '2026-07-03', '2026-07-02', '2026-07-01', '2026-07-05'])
  expect(sortWorkbookRows(rows, { key: 'test', order: 'descend' }).map(row => row.date)).toEqual(['2026-07-01', '2026-07-02', '2026-07-03', '2026-07-04', '2026-07-05'])
  expect(rows[0].date).toBe('2026-07-01')
  const small: WorkbookRow[] = ['2E-8', '0.00000001', '0'].map((value, index) => ({ date: String(index), cells: { test: { value, status: 'complete' } } }))
  expect(sortWorkbookRows(small, { key: 'test', order: 'ascend' }).map(row => row.date)).toEqual(['2', '1', '0'])
})

it('copies original decimals with column headers and meaningful missing-data states', () => {
  const text = workbookClipboardText([{ date: '2026-07-01', cells: { a: { value: '1234.5000', status: 'complete' }, b: { value: '0', status: 'adjusted' }, c: { value: null, status: 'missing_reading' } } }], ['a', 'b', 'c'].map(key => ({ key, label: key, unit: 'm³', quantity_kind: 'volume', value_kind: 'reading' })))
  expect(text).toBe('日期\ta\tb\tc\n2026-07-01\t1234.5\t0\t待补数')
  expect(needsWorkbookAttention({ value: '0', status: 'complete' })).toBe(false)
  expect(needsWorkbookAttention({ value: null, status: 'not_applicable' })).toBe(false)
  expect(needsWorkbookAttention({ value: null, status: 'pending_review' })).toBe(true)
  expect(workbookCellText({ value: null, status: 'not_applicable' })).toBe('不适用')
})

it('copies source results with review status and a real difference or unavailable calculation', () => {
  const provenance = { source_comparison: { reported_value: '53592', difference: '3592', calculation_status: 'complete', source: '循环水量!C6' } }
  expect(workbookCellText({ value: null, calculated_value: '50000', status: 'pending_review', provenance })).toBe('待核对；原表值：53592；系统计算值：50000；差异（原表－系统）：3592')
  expect(workbookCellText({ value: null, calculated_value: null, status: 'pending_review', provenance: { source_comparison: { ...provenance.source_comparison, reported_value: '0', difference: null, calculation_status: 'abnormal_dependency' } } })).toContain('原表值：0；系统计算值：无法重算（来源存在异常）；差异（原表－系统）：无法计算')
})
