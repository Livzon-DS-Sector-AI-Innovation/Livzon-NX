/* @vitest-environment happy-dom */
/* eslint-disable @typescript-eslint/no-explicit-any */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it } from 'vitest'

import DRTable from './DRTable'

const DATA = [
  {
    tank_date: '2026-08-01',
    batch_no: 'DR-2601',
    impurities: { impurity_6: 1, impurity_1: 2, purity: 98.5 },
    tanks: [
      {
        tank_no: '1#',
        handover_unit: 5,
        handover_volume: 20,
        fermentation_product_qty: 50.5,
        actual_product_qty: 48,
        handover_product_qty: 46,
        bacteria_residue_plates: 3,
        extractions: [
          {
            feeding_time: '08:00',
            extraction_batch_no: 'DR-E1',
            feeding_plates: 12,
            extraction_product_qty: 40,
            total_qty: 42,
            single_batch_yield: 0.8,
            fermentation_liquid_yield: 0.85,
            filtrates: [
              { tank_no: '1#', volume: 10, potency: 500, product_qty: 20 },
              { tank_no: '2#', volume: 8, potency: 400, product_qty: 15 },
            ],
          },
        ],
      },
    ],
  },
]

describe('DRTable', () => {
  let root: Root
  let container: HTMLElement

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
  })

  it('renders nested table with flattened rows', () => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<DRTable data={DATA} />)
    })
    const text = container.textContent || ''
    expect(text).toContain('DR-2601')
    expect(text).toContain('1#')
    expect(text).toContain('DR-E1')
  })

  it('renders empty placeholder when data is empty', () => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<DRTable data={[]} />)
    })
    expect(container.textContent || '').toContain('暂无数据')
  })
})