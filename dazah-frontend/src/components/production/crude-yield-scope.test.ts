import { describe, expect, it } from 'vitest'
import {
  applyCrudeYieldScope,
  crudeCumulativeYieldPercent,
  hasCrudeOutput,
} from './crude-yield'

// 2026-11-10 业务确认：尚未产出粗品的批次不参与收率口径
// （趋势图留空、平均收率剔除、累计收率分子分母同步剔除）。

describe('hasCrudeOutput', () => {
  it('仅产品量为正数视为已产出', () => {
    expect(hasCrudeOutput(1378.7)).toBe(true)
    expect(hasCrudeOutput(0)).toBe(false)
    expect(hasCrudeOutput(null)).toBe(false)
    expect(hasCrudeOutput(undefined)).toBe(false)
  })
})

describe('applyCrudeYieldScope', () => {
  it('未产出批次收率置空，已产出批次保留', () => {
    const rows = [
      { crude_product_qty: 1378.7, yield_rate: 100.16 },
      { crude_product_qty: 0, yield_rate: 0 },
      { crude_product_qty: null, yield_rate: 97.1 },
    ]
    const out = applyCrudeYieldScope(rows)
    expect(out[0].yield_rate).toBe(100.16)
    expect(out[1].yield_rate).toBeNull()
    expect(out[2].yield_rate).toBeNull()
  })

  it('不改动产品量等其他字段', () => {
    const out = applyCrudeYieldScope([
      { total_input: 2389.3, crude_product_qty: 0, yield_rate: 0 },
    ])
    expect(out[0].total_input).toBe(2389.3)
    expect(out[0].crude_product_qty).toBe(0)
  })
})

describe('crudeCumulativeYieldPercent', () => {
  it('仅统计已产出批次（分子分母同步剔除）', () => {
    const rows = [
      { total_input: 2389.3, crude_product_qty: 1378.7 },
      { total_input: 2934.1, crude_product_qty: 0 }, // 在产批次：剔除
      { total_input: 2650.8, crude_product_qty: null }, // 无数据批次：剔除
    ]
    // 1378.7 / 2389.3 = 57.7%
    expect(crudeCumulativeYieldPercent(rows)).toBe(57.7)
  })

  it('全部未产出或空数据返回 null', () => {
    expect(crudeCumulativeYieldPercent([{ total_input: 100, crude_product_qty: 0 }])).toBeNull()
    expect(crudeCumulativeYieldPercent([])).toBeNull()
  })
})
