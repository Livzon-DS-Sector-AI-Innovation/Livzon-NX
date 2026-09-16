/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// 粒子层是 canvas 动效，happy-dom 无 2D 上下文，mock 成静态占位
vi.mock('@/components/production/progress-particles', () => ({
  default: ({ progressPct }: { progressPct: number }) => (
    <div data-testid="progress-particles" data-pct={progressPct} />
  ),
}))

import BatchProgressBar from '@/components/production/batch-progress-bar'

describe('BatchProgressBar', () => {
  let root: Root
  let container: HTMLElement

  beforeEach(() => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  async function render(props: Parameters<typeof BatchProgressBar>[0]) {
    act(() => {
      root.render(<App><BatchProgressBar {...props} /></App>)
    })
    await act(async () => {
      await new Promise(r => setTimeout(r, 40))
    })
  }

  const seg = (key: string) =>
    container.querySelector(`[data-testid="batch-seg-${key}"]`) as
      | HTMLElement
      | null
  const arrow = () =>
    container.querySelector('[data-testid="batch-progress-arrow"]') as
      | HTMLElement
      | null
  const rest = () =>
    container.querySelector('[data-testid="batch-seg-rest"]') as
      | HTMLElement
      | null

  it('常规数据：四段渲染，箭头 clamp 定位，残余段按批次比例分摊', async () => {
    // 已完成=0，待产出=21，运行中=9，未开始=4，总=34
    await render({
      doneCount: 0,
      pendingCount: 21,
      runningCount: 9,
      idleCount: 4,
      doneYieldKg: null,
      plannedCapacityKg: null,
    })
    // 未设产能 → 批次口径：已完成 0% 不渲染，箭头钳在最左
    expect(seg('done')).toBeNull()
    expect(seg('pending')).toBeTruthy()
    expect(seg('running')).toBeTruthy()
    expect(seg('idle')).toBeTruthy()
    // 残余容器左垫 17px（箭头收尖段覆盖区），子段按内容区百分比
    expect(rest()?.style.paddingLeft).toBe('17px')
    // 残余段按批次比例分摊（rest=34）：待产出 21/34 ≈ 61.76%、运行中 9/34 ≈ 26.47%
    expect(seg('pending')?.style.width).toBe(`${(21 / 34) * 100}%`)
    expect(seg('running')?.style.width).toBe(`${(9 / 34) * 100}%`)
    // 未开始段 flex:1 吃掉其余（4/34 ≈ 11.76% + 浮点残差）
    expect(seg('idle')?.className).toContain('flex-1')
    // 分界点 0% → left 被 clamp 到 0px
    expect(arrow()?.getAttribute('data-boundary-pct')).toBe('0.0000000000')
    // 图例四项
    const text = container.textContent || ''
    ;['已完成', '待出产量', '运行中', '未开始'].forEach(label =>
      expect(text).toContain(label),
    )
  })

  it('边界1：待产出=0 → 无 34px 垫入，箭头贴最左', async () => {
    // 已完成=0，待产出=0，运行中=10，未开始=0，总=10
    await render({
      doneCount: 0,
      pendingCount: 0,
      runningCount: 10,
      idleCount: 0,
      doneYieldKg: null,
      plannedCapacityKg: null,
    })
    expect(seg('pending')).toBeNull()
    expect(seg('running')).toBeTruthy()
    expect(seg('idle')).toBeNull()
    // 运行中段显式 100% 撑满残余容器
    expect(arrow()?.getAttribute('data-boundary-pct')).toBe('0.0000000000')
  })

  it('边界2：全为待产出 → 段占满轨道不溢出，箭头仍钳最左', async () => {
    // 已完成=0，待产出=10，运行中=0，未开始=0，总=10
    await render({
      doneCount: 0,
      pendingCount: 10,
      runningCount: 0,
      idleCount: 0,
      doneYieldKg: null,
      plannedCapacityKg: null,
    })
    expect(seg('pending')).toBeTruthy()
    // maxWidth 100% 兜底：即使占比 100% + 17px 也不允许把轨道撑宽
    expect(seg('pending')?.style.maxWidth).toBe('100%')
    expect(seg('running')).toBeNull()
    expect(seg('idle')).toBeNull()
  })

  it('比例回归：运行中 2 批 / 未开始 9 批长度比 = 2:9，不再等长', async () => {
    // 旧实现运行中/未开始均为 flex:1 → 等分剩余空间，批次数不参与宽度（错）
    await render({
      doneCount: 0,
      pendingCount: 0,
      runningCount: 2,
      idleCount: 9,
      doneYieldKg: null,
      plannedCapacityKg: null,
    })
    // 残余容器内：运行中显式 2/11 ≈ 18.18%，未开始 flex:1 吃掉其余 ≈ 81.82%
    expect(seg('running')?.style.width).toBe(`${(2 / 11) * 100}%`)
    expect(seg('idle')?.className).toContain('flex-1')
  })

  it('产能口径：已完成段=达成率%，箭头尖端落在分界点；粒子跟随', async () => {
    // 20/31 批完成，产能 571,417.71/945,500 → 60.44%
    await render({
      doneCount: 20,
      pendingCount: 1,
      runningCount: 2,
      idleCount: 8,
      doneYieldKg: 571417.71,
      plannedCapacityKg: 945500,
    })
    // 已完成段剪 17px（由箭头右半收尖段补回）；箭头 left = 达成率% − 34px，
    // 中点（left + 17px）恰锚定已完成矩形右缘（达成率% − 17px）
    expect(seg('done')?.style.width).toBe('calc(60.43550608143838% - 17px)')
    expect(arrow()?.getAttribute('data-arrow-left')).toBe(
      'clamp(0px, calc(60.43550608143838% - 34px), calc(100% - 34px))',
    )
    expect(arrow()?.getAttribute('data-boundary-pct')).toMatch(/^60\.4355/)
    const particles = container.querySelector('[data-testid="progress-particles"]')
    expect(particles?.getAttribute('data-pct')).toBe('60.43550608143838')
  })

  it('产能达成 100%：箭头钳在最右，不跑出容器', async () => {
    await render({
      doneCount: 30,
      pendingCount: 1,
      runningCount: 0,
      idleCount: 0,
      doneYieldKg: 945500,
      plannedCapacityKg: 945500,
    })
    expect(arrow()?.getAttribute('data-boundary-pct')).toBe('100.0000000000')
    // 矩形剪 17px、箭头钳最右，尖端贴轨道右缘
    expect(seg('done')?.style.width).toBe('calc(100% - 17px)')
    expect(arrow()?.getAttribute('data-arrow-left')).toBe(
      'clamp(0px, calc(100% - 34px), calc(100% - 34px))',
    )
  })

  it('口径切换：切到批次口径后段宽与箭头重算', async () => {
    await render({
      doneCount: 20,
      pendingCount: 1,
      runningCount: 2,
      idleCount: 8,
      doneYieldKg: 571417.71,
      plannedCapacityKg: 945500,
    })
    // 默认产能口径 60.44%
    expect(seg('done')?.style.width).toBe('calc(60.43550608143838% - 17px)')
    // 点击「批次数量」切换：20/31 ≈ 64.52%
    const option = Array.from(container.querySelectorAll('.ant-segmented-item')).find(
      item => item.textContent?.includes('批次数量'),
    ) as HTMLElement
    expect(option).toBeTruthy()
    await act(async () => {
      option.click()
      await new Promise(r => setTimeout(r, 60))
    })
    expect(seg('done')?.style.width).toBe('calc(64.51612903225806% - 17px)')
    expect(arrow()?.getAttribute('data-boundary-pct')).toMatch(/^64\.5161/)
  })

  it('历史周期：隐藏口径切换器', async () => {
    await render({
      doneCount: 5,
      pendingCount: 0,
      runningCount: 0,
      idleCount: 0,
      doneYieldKg: 100,
      plannedCapacityKg: 945500,
      historical: true,
    })
    expect(container.querySelector('.ant-segmented')).toBeNull()
  })
})
