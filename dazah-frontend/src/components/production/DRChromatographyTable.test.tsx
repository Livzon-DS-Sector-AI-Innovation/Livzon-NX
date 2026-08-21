/* @vitest-environment happy-dom */
/* eslint-disable @typescript-eslint/no-explicit-any */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it } from 'vitest'

import DRChromatographyTable from './DRChromatographyTable'

const DATA = [
  { id: 1, fl_batch_no: 'DR-F1', production_date: '2026-08-01', chromatography_batch_no: 'DR-C1', column_no: 'A',
    extraction_batch_no: 'DR-E1', volume_kl: 10, potency_mg_l: 500, product_qty_kg: 20 },
  { id: 2, fl_batch_no: 'DR-F1', production_date: '2026-08-01', chromatography_batch_no: 'DR-C1', column_no: 'A',
    extraction_batch_no: 'DR-E1', volume_kl: 8, potency_mg_l: 400, product_qty_kg: 15 },
  { id: 3, fl_batch_no: 'DR-F2', production_date: '2026-08-02', chromatography_batch_no: 'DR-C2', column_no: 'B',
    extraction_batch_no: 'DR-E2', volume_kl: 12, potency_mg_l: 600, product_qty_kg: 25 },
]

describe('DRChromatographyTable', () => {
  let root: Root
  let container: HTMLElement

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
  })

  it('renders table with merged cell values', () => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<DRChromatographyTable data={DATA} />)
    })
    const text = container.textContent || ''
    expect(text).toContain('DR-C1')
    expect(text).toContain('DR-E1')
    expect(text).toContain('10.00')
  })

  it('renders empty placeholder when no data', () => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<DRChromatographyTable data={[]} />)
    })
    expect(container.textContent || '').toContain('暂无数据')
  })
})