import { describe, expect, it } from 'vitest'
import { monthPeriod, resolveMonth } from './energy-period'

describe('energy calendar month filters', () => {
  it('selects a year and month and compares calendar months of different lengths', () => {
    expect(monthPeriod(2026, 7)).toEqual({ start: '2026-07-01', end: '2026-07-31', previousStart: '2026-06-01', previousEnd: '2026-06-30', yearStart: '2025-07-01', yearEnd: '2025-07-31' })
    expect(monthPeriod(2024, 3).previousEnd).toBe('2024-02-29')
    expect(monthPeriod(2024, 2).yearEnd).toBe('2023-02-28')
  })
  it('keeps old dated links usable while selecting the whole month', () => {
    expect(resolveMonth(new URLSearchParams('start_date=2026-07-02'))).toEqual({ year: 2026, month: 7 })
    expect(resolveMonth(new URLSearchParams('year=2025&month=12'))).toEqual({ year: 2025, month: 12 })
  })
})
