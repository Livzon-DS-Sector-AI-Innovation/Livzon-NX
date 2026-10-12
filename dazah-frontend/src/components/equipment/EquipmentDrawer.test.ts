/* @vitest-environment happy-dom */

import { describe, expect, it, vi } from 'vitest'

vi.mock('@/stores/equipment', () => ({ useEquipmentStore: () => ({}) }))
vi.mock('@/actions/equipment', () => ({
  createEquipment: vi.fn(),
  updateEquipment: vi.fn(),
}))

import { formatTechParams, parseTechParams } from './EquipmentDrawer'

describe('technical params text conversion', () => {
  it('parses each line into a param object and trims whitespace', () => {
    expect(parseTechParams('功率：3kW\n容积 = 500L\n转速: 60rpm\n\n')).toEqual({
      功率: '3kW',
      容积: '500L',
      转速: '60rpm',
    })
  })

  it('returns undefined for blank input', () => {
    expect(parseTechParams(undefined)).toBeUndefined()
    expect(parseTechParams('  \n ')).toBeUndefined()
  })

  it('rejects a line without a separator and reports its line number', () => {
    expect(() => parseTechParams('功率：3kW\n功率参数')).toThrow(
      '技术参数第 2 行格式不正确',
    )
  })

  it('formats a params object back to one param per line', () => {
    expect(formatTechParams({ 功率: '3kW', 容积: '500L' })).toBe(
      '功率：3kW\n容积：500L',
    )
    expect(formatTechParams(null)).toBeUndefined()
    expect(formatTechParams({})).toBeUndefined()
  })

  it('round-trips parse and format without losing values', () => {
    const text = '功率：3kW\n容积：500L'
    expect(formatTechParams(parseTechParams(text))).toBe(text)
  })
})
