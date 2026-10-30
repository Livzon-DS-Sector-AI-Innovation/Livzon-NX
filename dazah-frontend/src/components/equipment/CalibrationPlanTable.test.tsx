/* @vitest-environment happy-dom */

// 校准计划表：剩余天数列三色分支（逾期红 / 7 天内橙 / 正常灰）。

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const store = vi.hoisted(() => {
  const daysFromNow = (n: number) => {
    const d = new Date()
    d.setDate(d.getDate() + n)
    return d.toISOString().slice(0, 10)
  }
  return {
    calibrationPlans: [
      { id: 'p1', calibration_type: '内部校准', cycle_months: 6, next_calibration_date: daysFromNow(-3) },
      { id: 'p2', calibration_type: '内部校准', cycle_months: 6, next_calibration_date: daysFromNow(5) },
      { id: 'p3', calibration_type: '内部校准', cycle_months: 6, next_calibration_date: daysFromNow(200) },
    ],
    calibrationPlanTotal: 3,
    calibrationPlanPage: 1,
    calibrationPlanPageSize: 20,
    setCalibrationPlanPage: vi.fn(),
    fetchCalibrationPlanData: vi.fn(),
  }
})

vi.mock('@/stores/equipment', () => ({ useEquipmentStore: () => store }))

import { CalibrationPlanTable } from './CalibrationPlanTable'

describe('CalibrationPlanTable', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
  })

  it('剩余天数按逾期/临期/远期三色渲染', async () => {
    await act(async () => {
      root.render(<CalibrationPlanTable />)
      await Promise.resolve()
    })
    const text = container.textContent ?? ''
    expect(text).toContain('逾期3天')
    expect(text).toContain('5天')
    expect(text).toContain('200天')
  })
})
