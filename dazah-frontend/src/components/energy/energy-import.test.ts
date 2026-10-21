import { describe, expect, it } from 'vitest'
import type { ImportPreview } from '@/lib/api/energy-ledger'
import { importRows } from './energy-import'

describe('energy import input boundaries', () => {
  it('does not offer cached totals or output values as readings or adjustments', () => {
    const preview: ImportPreview = { id: 'batch', status: 'preview', payload: { formulas: [], sheets: [
      { name: '电量', category: 'electricity', headers: ['日期', '总计', '设备', '小计'], calculated_columns: [2, 4], input_columns: [3], cells: [{ column: 2, date: '2026-07-01', value: '100' }, { column: 3, date: '2026-07-01', value: '0' }, { column: 4, date: '2026-07-01', value: '100' }] },
      { name: '101车间', category: null, headers: ['日期', '电'], cells: [{ column: 2, date: '2026-07-01', value: '100' }] },
    ] } }
    expect(importRows(preview)).toEqual({ columns: [{ key: '电量:3', sheet: '电量', column: 3, label: '设备', count: 1 }], manualRows: [] })
  })
  it('offers a literal override only when that column has real formula evidence', () => {
    const preview: ImportPreview = { id: 'batch', status: 'preview', payload: { formulas: [{ sheet: '蒸汽量', cell: 'B3', formula: '=蒸汽码!B4-蒸汽码!B3' }], sheets: [{ name: '蒸汽量', category: null, headers: ['日期', '蒸汽', '未知结果'], cells: [{ column: 2, date: '2026-07-01', value: '0' }, { column: 3, date: '2026-07-01', value: '0' }] }] } }
    expect(importRows(preview).manualRows).toEqual([{ key: '蒸汽量:2:2026-07-01', sheet: '蒸汽量', label: '蒸汽', date: '2026-07-01', value: '0' }])
  })
  it('requires a current server input classification before offering legacy columns', () => {
    const preview: ImportPreview = { id: 'old', status: 'preview', payload: { sheets: [{ name: '电量', category: 'electricity', headers: ['日期', '总计'], cells: [{ column: 2, date: '2026-07-01', value: '100' }] }] } }
    expect(importRows(preview).columns).toEqual([])
  })
})
