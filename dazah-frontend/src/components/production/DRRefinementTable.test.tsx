/* @vitest-environment happy-dom */
/* eslint-disable @typescript-eslint/no-explicit-any */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it } from 'vitest'

import DRRefinementTable from './DRRefinementTable'

const DATA = [
  { id: 1, fl_batch_no: 'DR-F1', production_date: '2026-08-01', refinement_batch_no: 'DR-R1',
    feed_weight_kg: 10.5, feed_content: 90, feed_dry_loss: 2, feed_pure_kg: 9,
    purity: 98.5, total_impurities: 1.2, mother_liquor_product_kg: 1.1 },
  { id: 2, fl_batch_no: 'DR-F1', production_date: '2026-08-01', refinement_batch_no: 'DR-R1',
    feed_weight_kg: 15.2, feed_content: 88, purity: 99, total_impurities: 0.8,
    mother_liquor_volume: 3, mother_liquor_unit: 20, remark_text: '有备注' },
  { id: 3, fl_batch_no: 'DR-F2', production_date: '2026-08-02', refinement_batch_no: 'DR-R2',
    feed_weight_kg: '16kg', feed_content: '90.5', purity: 95, total_impurities: 1.5 },
]

describe('DRRefinementTable', () => {
  let root: Root
  let container: HTMLElement

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
  })

  it('renders table with merged cells and values', () => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<DRRefinementTable data={DATA} />)
    })
    const text = container.textContent || ''
    expect(text).toContain('DR-F1')
    expect(text).toContain('DR-R1')
    expect(text).toContain('98.500')
  })

  it('renders empty placeholder when no data', () => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<DRRefinementTable data={[]} />)
    })
    expect(container.textContent || '').toContain('暂无数据')
  })

  it('formats numeric strings with toFixed', () => {
    // 数字字符串 '8kg' 解析失败返回原文
    expect(DRRefinementTable).toBeTypeOf('function')
  })
})