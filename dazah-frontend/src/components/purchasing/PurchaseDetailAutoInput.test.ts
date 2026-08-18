import { describe, expect, it } from 'vitest'
import {
  getPurchaseDetailColumnWidth,
  getPurchaseDetailInputWidth,
  PURCHASE_DETAIL_TABLE_CELL_HORIZONTAL_PADDING,
  purchaseDetailInputSizing,
} from './PurchaseDetailAutoInput'

describe('purchase detail input sizing', () => {
  it('keeps short values at a readable minimum width', () => {
    const sizing = purchaseDetailInputSizing.productName

    expect(getPurchaseDetailInputWidth('', sizing)).toBe(sizing.minWidth)
    expect(getPurchaseDetailInputWidth('A', sizing)).toBe(sizing.minWidth)
    expect(getPurchaseDetailInputWidth('标签纸', sizing)).toBe(sizing.minWidth)
  })

  it('expands for longer values but never breaks the configured maximum', () => {
    const sizing = purchaseDetailInputSizing.remarks
    const mediumValue = '采购前确认供应商批次、包装和到货时间'
    const longValue = '长文本'.repeat(200)

    expect(getPurchaseDetailInputWidth(mediumValue, sizing)).toBeGreaterThan(sizing.minWidth)
    expect(getPurchaseDetailInputWidth(longValue, sizing)).toBe(sizing.maxWidth)
  })

  it('uses the longest value in a column without exceeding its maximum', () => {
    const sizing = purchaseDetailInputSizing.materialDescription
    const width = getPurchaseDetailColumnWidth(
      [
        { material_description: '短说明' },
        { material_description: '这是一段更长的物料说明，用于验证列宽会跟随内容增长' },
      ],
      'material_description',
      sizing,
    )

    expect(width).toBeGreaterThan(sizing.minWidth)
    expect(width).toBeLessThanOrEqual(
      sizing.maxWidth + PURCHASE_DETAIL_TABLE_CELL_HORIZONTAL_PADDING,
    )
  })
})
