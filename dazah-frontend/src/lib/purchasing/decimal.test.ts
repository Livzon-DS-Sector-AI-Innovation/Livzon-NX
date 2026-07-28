import { describe, expect, it } from 'vitest'

import { isPresentDecimal, sumMoney, sumQuantity } from './decimal'

describe('purchasing decimal helpers', () => {
  it('adds currency values without floating-point rounding errors', () => {
    expect(sumMoney(['0.10', '0.20', '¥1,000.00'])).toBe('¥1000.30')
  })

  it('preserves the highest quantity precision and trims trailing zeroes', () => {
    expect(sumQuantity(['1.250', 2, '-0.05'])).toBe('3.2')
  })

  it('distinguishes valid zero values from missing or invalid input', () => {
    expect(isPresentDecimal(0)).toBe(true)
    expect(isPresentDecimal('0.00')).toBe(true)
    expect(isPresentDecimal('not-a-number')).toBe(false)
    expect(isPresentDecimal(null)).toBe(false)
  })
})
