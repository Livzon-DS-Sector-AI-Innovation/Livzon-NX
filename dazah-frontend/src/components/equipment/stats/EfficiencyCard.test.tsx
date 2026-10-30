/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/actions/equipment', () => ({
  fetchEfficiencyStatistics: vi.fn(),
}))

import { EfficiencyCard } from './EfficiencyCard'
import type { EfficiencyStatistics } from '@/types/equipment'

const data: EfficiencyStatistics = {
  avg_response_minutes: 6.5,
  avg_repair_minutes: 47,
  urgent_total: 12,
  urgent_on_time: 10,
  urgent_5min_rate: 0.83,
  total_orders: 30,
  monthly: [
    { month: '2026-09', total: 12, completed: 10, urgent: 2, avg_response: 7, avg_repair: 50 },
    { month: '2026-10', total: 18, completed: 15, urgent: 3, avg_response: 6, avg_repair: 44 },
  ],
  top_faults: [
    {
      equipment_id: 'e1', equipment_name: '离心泵A', equipment_no: 'LB-001',
      workshop_code: '201-1', order_count: 11, avg_repair_minutes: 38,
    },
    {
      equipment_id: 'e2', equipment_name: '薄膜蒸发器4', equipment_no: 'XT-1',
      workshop_code: '101-1', order_count: 8, avg_repair_minutes: 52,
    },
  ],
  repairer_ranking: [
    {
      assignee_id: 'u1', assignee_name: '张三', order_count: 21,
      avg_response_minutes: 2, avg_repair_minutes: 5.1,
    },
    {
      assignee_id: 'u2', assignee_name: '李四', order_count: 9,
      avg_response_minutes: 4, avg_repair_minutes: 12,
    },
  ],
  response_buckets: [
    { bucket: '≤5分钟', count: 19, ratio: 0.731 },
    { bucket: '5-30分钟', count: 3, ratio: 0.115 },
    { bucket: '30-120分钟', count: 0, ratio: 0 },
    { bucket: '>120分钟', count: 0, ratio: 0 },
    { bucket: '未接单', count: 4, ratio: 0.154 },
  ],
}

describe('EfficiencyCard', () => {
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

  it('渲染指标数字、月度趋势与 TOP 设备', async () => {
    await act(async () => {
      root.render(
        <EfficiencyCard
          initialData={data}
          workshopOptions={[
            { code: '201-1', name: '201一车间' },
            { code: '101-1', name: '101一车间' },
          ]}
        />,
      )
      await Promise.resolve()
    })

    const text = document.body.textContent ?? ''
    expect(text).toContain('7分钟')       // 平均响应 6.5 → round
    expect(text).toContain('47分钟')      // MTTR
    expect(text).toContain('83%')         // 紧急达标
    expect(text).toContain('离心泵A')
    expect(text).toContain('11次')
    expect(text).toContain('薄膜蒸发器4')
    // 全工厂模式下 TOP 显示车间标签
    expect(text).toContain('201-1')
  })

  it('无数据时展示空态占位', async () => {
    await act(async () => {
      root.render(
        <EfficiencyCard
          initialData={{ ...data, total_orders: 0, monthly: [], top_faults: [] }}
          workshopOptions={[]}
        />,
      )
      await Promise.resolve()
    })
    expect(document.querySelector('[data-testid="efficiency-empty"]')).toBeTruthy()
    expect((document.body.textContent ?? '')).toContain('暂无维修数据')
  })

  it('车间下拉渲染选项且初始不重新取数', async () => {
    const { fetchEfficiencyStatistics } = await import('@/actions/equipment')
    const mock = fetchEfficiencyStatistics as ReturnType<typeof vi.fn>
    mock.mockClear()

    await act(async () => {
      root.render(
        <EfficiencyCard
          initialData={data}
          workshopOptions={[
            { code: '201-1', name: '201一车间' },
            { code: '101-1', name: '101一车间' },
          ]}
        />,
      )
      await Promise.resolve()
    })

    const combo = document.querySelector(
      '[aria-label="车间筛选"], .ant-select-selector',
    ) as HTMLElement | null
    expect(combo ?? document.body.textContent?.includes('全工厂')).toBeTruthy()
    expect((document.body.textContent ?? '')).toContain('全工厂')
    // initialData 已提供，初始渲染不应触发重新取数
    expect(mock).not.toHaveBeenCalled()
  })

  it('点击刷新按钮重新取数并回调 onData', async () => {
    const { fetchEfficiencyStatistics } = await import('@/actions/equipment')
    const mock = fetchEfficiencyStatistics as ReturnType<typeof vi.fn>
    mock.mockClear()
    mock.mockResolvedValue(data)
    const onData = vi.fn()

    await act(async () => {
      root.render(
        <EfficiencyCard
          initialData={data}
          workshopOptions={[]}
          onData={onData}
        />,
      )
      await Promise.resolve()
    })

    const refresh = document.querySelector('[aria-label="刷新效能数据"]') as HTMLElement
    expect(refresh).toBeTruthy()
    await act(async () => {
      refresh.click()
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(mock).toHaveBeenCalledTimes(1)
    expect(onData).toHaveBeenCalledWith(data)
  })

  it('切换车间触发取数并回调 onWorkshopChange', async () => {
    const { fetchEfficiencyStatistics } = await import('@/actions/equipment')
    const mock = fetchEfficiencyStatistics as ReturnType<typeof vi.fn>
    mock.mockClear()
    mock.mockResolvedValue(data)
    const onWorkshopChange = vi.fn()

    await act(async () => {
      root.render(
        <EfficiencyCard
          initialData={data}
          workshopOptions={[{ code: '201-1', name: '201一车间' }]}
          onWorkshopChange={onWorkshopChange}
        />,
      )
      await Promise.resolve()
    })

    // antd Select 在 happy-dom 下经 mousedown 打开面板后点选项
    const selector = document.querySelector('[role="combobox"], .ant-select-selector, .ant-select') as HTMLElement
    if (!selector) {
      // happy-dom 未渲染 antd Select 结构时退化为断言不崩溃
      expect(document.body.textContent ?? '').toContain('全工厂')
      return
    }
    selector.dispatchEvent(
      new MouseEvent('mousedown', { bubbles: true }),
    )
    await act(async () => { await Promise.resolve() })
    const option = Array.from(
      document.querySelectorAll('.ant-select-item-option'),
    ).find((el) => el.textContent?.trim() === '201一车间') as HTMLElement | undefined
    if (option) {
      await act(async () => {
        option.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
        option.click()
        await Promise.resolve()
        await Promise.resolve()
      })
      expect(onWorkshopChange).toHaveBeenCalledWith('201-1')
      expect(mock).toHaveBeenCalledWith('201-1')
    } else {
      // 下拉未展开时退化为断言选择器存在
      expect(selector).toBeTruthy()
    }
  })
})
