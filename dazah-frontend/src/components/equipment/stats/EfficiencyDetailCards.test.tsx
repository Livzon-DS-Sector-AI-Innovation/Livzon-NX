/* @vitest-environment happy-dom */

// 维修人员排行卡 + 响应时效分布卡：渲染、空态与汇总口径。

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { KpiCard } from './KpiCard'
import { RepairerRankCard } from './RepairerRankCard'
import { ResponseBucketCard } from './ResponseBucketCard'
import type { EfficiencyRepairerRank, EfficiencyResponseBucket } from '@/types/equipment'

const ranking: EfficiencyRepairerRank[] = [
  { assignee_id: 'u1', assignee_name: '秦佳豪', order_count: 21, avg_response_minutes: 2, avg_repair_minutes: 5.1 },
  { assignee_id: 'u2', assignee_name: '李四', order_count: 9, avg_response_minutes: 4, avg_repair_minutes: 72 },
]

const buckets: EfficiencyResponseBucket[] = [
  { bucket: '≤5分钟', count: 19, ratio: 0.731 },
  { bucket: '5-30分钟', count: 3, ratio: 0.115 },
  { bucket: '30-120分钟', count: 0, ratio: 0 },
  { bucket: '>120分钟', count: 0, ratio: 0 },
  { bucket: '未接单', count: 4, ratio: 0.154 },
]

describe('RepairerRankCard', () => {
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

  it('渲染排行姓名、接单数与汇总行', async () => {
    await act(async () => {
      root.render(<RepairerRankCard ranking={ranking} workshopLabel="201一车间" />)
    })
    const text = container.textContent ?? ''
    expect(text).toContain('维修人员排行')
    expect(text).toContain('201一车间')
    expect(text).toContain('秦佳豪')
    expect(text).toContain('李四')
    expect(text).toContain('共 2 人接单 · 合计 30 单')
    // 均修复 72 分钟 → 1小时12分
    expect(text).toContain('1小时12分')
  })

  it('行 hover 高亮与移出还原', async () => {
    await act(async () => {
      root.render(<RepairerRankCard ranking={ranking} workshopLabel="全工厂" />)
    })
    const row = container.querySelector('[data-testid="repairer-rank-row"]') as HTMLElement
    expect(row).toBeTruthy()
    // React 的 onMouseEnter/Leave 由 mouseover/mouseout 派生
    await act(async () => {
      row.dispatchEvent(new MouseEvent('mouseover', { bubbles: true, relatedTarget: document.body }))
    })
    expect(row.style.background).toContain('faf9f8')
    await act(async () => {
      row.dispatchEvent(new MouseEvent('mouseout', { bubbles: true, relatedTarget: document.body }))
    })
    expect(row.style.background).toBe('transparent')
  })

  it('空排行显示引导文案', async () => {
    await act(async () => {
      root.render(<RepairerRankCard ranking={[]} workshopLabel="全工厂" />)
    })
    const text = container.textContent ?? ''
    expect(text).toContain('暂无接单数据')
    expect(text).toContain('维修人员接单后展示排行')
  })
})

describe('ResponseBucketCard', () => {
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

  it('渲染五档图例、占比与已接单/未接单汇总', async () => {
    await act(async () => {
      root.render(<ResponseBucketCard buckets={buckets} workshopLabel="全工厂" />)
    })
    const text = container.textContent ?? ''
    expect(text).toContain('响应时效分布')
    expect(text).toContain('已接单 22 · 未接单 4')
    expect(text).toContain('≤5分钟')
    expect(text).toContain('19单')
    expect(text).toContain('73%')
    expect(text).toContain('未接单')
  })

  it('无工单显示空态', async () => {
    await act(async () => {
      root.render(
        <ResponseBucketCard
          buckets={buckets.map((b) => ({ ...b, count: 0, ratio: 0 }))}
          workshopLabel="全工厂"
        />,
      )
    })
    expect(container.textContent ?? '').toContain('暂无工单数据')
  })
})

describe('KpiCard', () => {
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

  it('可点击卡片支持鼠标与键盘触发', async () => {
    const onClick = vi.fn()
    await act(async () => {
      root.render(
        <KpiCard
          label="待处理工单"
          value={1}
          suffix="单"
          icon={<span>icon</span>}
          accentColor="#fa8c16"
          index={0}
          onClick={onClick}
        />,
      )
    })
    const card = container.querySelector('.kpi-card') as HTMLElement
    expect(card).toBeTruthy()
    expect(card.getAttribute('role')).toBe('button')

    await act(async () => { card.click() })
    expect(onClick).toHaveBeenCalledTimes(1)

    await act(async () => {
      card.dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }),
      )
    })
    expect(onClick).toHaveBeenCalledTimes(2)
    await act(async () => {
      card.dispatchEvent(
        new KeyboardEvent('keydown', { key: ' ', bubbles: true }),
      )
    })
    expect(onClick).toHaveBeenCalledTimes(3)
    // 非触发键不调用
    await act(async () => {
      card.dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }),
      )
    })
    expect(onClick).toHaveBeenCalledTimes(3)
  })
})
