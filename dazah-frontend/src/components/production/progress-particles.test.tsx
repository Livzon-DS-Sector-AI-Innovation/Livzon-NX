/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import ProgressParticles from './progress-particles'

type Ctx = {
  calls: string[]
  arcs: Array<{ x: number; y: number; r: number }>
  setTransform: (...args: unknown[]) => void
  clearRect: (...args: unknown[]) => void
  save: () => void
  beginPath: () => void
  rect: (...args: unknown[]) => void
  clip: () => void
  fillRect: (...args: unknown[]) => void
  fill: () => void
  stroke: () => void
  restore: () => void
  createLinearGradient: () => {
    addColorStop: (offset: number, color: string) => void
  }
  arc: (x: number, y: number, r: number) => void
}

function makeCtx(): Ctx {
  const ctx: Ctx = {
    calls: [],
    arcs: [],
    setTransform: () => undefined,
    clearRect: () => undefined,
    save: () => undefined,
    beginPath: () => undefined,
    rect: () => undefined,
    clip: () => undefined,
    fillRect: () => undefined,
    fill: () => undefined,
    stroke: () => undefined,
    restore: () => undefined,
    createLinearGradient: () => ({ addColorStop: () => undefined }),
    arc: () => undefined,
  }
  const record = (name: string) => (...args: unknown[]) => {
    ctx.calls.push(`${name}:${args.length}`)
  }
  ctx.setTransform = record('setTransform')
  ctx.clearRect = record('clearRect')
  ctx.save = record('save')
  ctx.beginPath = record('beginPath')
  ctx.rect = record('rect')
  ctx.clip = record('clip')
  ctx.fillRect = record('fillRect')
  ctx.fill = record('fill')
  ctx.stroke = record('stroke')
  ctx.restore = record('restore')
  ctx.createLinearGradient = () => ({ addColorStop: () => undefined })
  ctx.arc = (x: number, y: number, r: number) => {
    ctx.calls.push('arc:3')
    ctx.arcs.push({ x, y, r })
  }
  return ctx
}

describe('ProgressParticles (canvas decoration layer)', () => {
  let root: Root
  let container: HTMLElement
  let ctx: Ctx
  let rafQueue: Array<{ id: number; cb: (now: number) => void }>
  let rafSeq: number
  let cancelled: number[]

  beforeEach(() => {
    container = document.createElement('div')
    vi.spyOn(container, 'getBoundingClientRect').mockReturnValue({
      width: 600,
      height: 12,
      x: 0,
      y: 0,
      top: 0,
      left: 0,
      right: 600,
      bottom: 12,
      toJSON: () => ({}),
    } as DOMRect)
    document.body.append(container)
    root = createRoot(container)
    ctx = makeCtx()
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(
      ctx as unknown as CanvasRenderingContext2D,
    )
    rafQueue = []
    rafSeq = 0
    cancelled = []
    vi.stubGlobal('requestAnimationFrame', (cb: (now: number) => void) => {
      rafSeq += 1
      rafQueue.push({ id: rafSeq, cb })
      return rafSeq
    })
    vi.stubGlobal('cancelAnimationFrame', (id: number) => {
      cancelled.push(id)
      rafQueue = rafQueue.filter((entry) => entry.id !== id)
    })
    window.localStorage.clear()
  })

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  async function render(props?: { progressPct?: number; ultra?: boolean }) {
    act(() => {
      root.render(
        <ProgressParticles
          progressPct={props?.progressPct ?? 60}
          ultra={props?.ultra ?? false}
        />,
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30))
    })
  }

  function tick(now: number) {
    const entries = [...rafQueue]
    rafQueue = []
    for (const entry of entries) {
      act(() => {
        entry.cb(now)
      })
    }
  }

  it('renders canvas, resizes, spawns streaming dots and draws them', async () => {
    await render()
    expect(container.querySelector('canvas')).toBeTruthy()
    // resize：以父元素尺寸 × dpr 设置画布
    expect(canvasWidth()).toBe(600)
    // 推进 ~3s（帧步长 100ms，dt 钳 0.05）：粒子在右端持续生成并绘制
    for (let i = 0; i < 30; i++) tick(1000 + i * 100)
    expect(ctx.calls.some((c) => c.startsWith('clearRect'))).toBe(true)
    expect(ctx.calls.some((c) => c.startsWith('clip'))).toBe(true)
    expect(ctx.arcs.length).toBeGreaterThan(0)
    // 帧循环继续排队
    expect(rafQueue.length).toBe(1)
    // 进度不变时 effect 不触发光泽（无异常即可）
    await render({ progressPct: 60 })
  })

  it('spawning is skipped when tip is tiny and unmount cancels raf', async () => {
    await render({ progressPct: 0 })
    tick(1000)
    for (let i = 0; i < 10; i++) tick(1000 + i * 100)
    // tip ≤ 4：spawn 直接返回，不绘制裁剪区
    expect(ctx.calls.some((c) => c.startsWith('clip'))).toBe(false)
    expect(ctx.arcs.length).toBe(0)
    act(() => root.unmount())
    expect(cancelled.length).toBeGreaterThan(0)
    // 卸载后无残留帧
    expect(rafQueue.length).toBe(0)
    // 标记 root 已卸载，afterEach 重复 unmount 安全
    root = createRoot(document.createElement('div'))
  })

  it('washes purple from the progress point on progress change', async () => {
    await render({ progressPct: 60 })
    tick(1000)
    const countFillRect = () =>
      ctx.calls.filter((c) => c.startsWith('fillRect')).length
    expect(countFillRect()).toBe(0)
    // 进度变化 → 1.2s 紫色微光自进度点向左回渗（渐变填充）
    await render({ progressPct: 75 })
    const now = performance.now()
    tick(now + 200)
    const during = countFillRect()
    expect(during).toBeGreaterThan(0)
    // 光泽 1.2s 后消散，不再新增绘制
    tick(now + 1600)
    tick(now + 2200)
    expect(countFillRect()).toBe(during)
    // 星点无方向性喷流与冲击波（不出现描边）
    expect(ctx.calls.some((c) => c.startsWith('stroke'))).toBe(false)
  })

  it('spawns at the right edge and streams leftward within the done segment', async () => {
    await render({ progressPct: 60 }) // tip = 600 × 60% = 360
    const minXPerTick: number[] = []
    // 推进 ~8s：粒子在最右端持续生成
    for (let i = 0; i < 80; i++) {
      tick(1000 + i * 100)
      const xs = ctx.arcs.slice(-40).map((a) => a.x)
      if (xs.length) minXPerTick.push(Math.min(...xs))
    }
    expect(ctx.arcs.length).toBeGreaterThan(0)
    // 全部位于已完成段内（进度点以内）
    const all = ctx.arcs.map((a) => a.x)
    expect(Math.min(...all)).toBeGreaterThanOrEqual(2)
    expect(Math.max(...all)).toBeLessThanOrEqual(360)
    // 向左流动：粒子从最右端一路流到接近左缘（min 随时间降至 ≤ 30）
    expect(Math.min(...minXPerTick)).toBeLessThanOrEqual(30)
    // 收尾时最左粒子已远离右端生成位置（358）
    expect(minXPerTick[minXPerTick.length - 1]).toBeLessThan(340)
    // 上下晃动错落：同一批绘制里粒子 y 不在同一条水平线上
    const ys = new Set(ctx.arcs.slice(-40).map((a) => Math.round(a.y)))
    expect(ys.size).toBeGreaterThan(1)
  })

  it('draws ultra density overlay and culls dots on progress shrink', async () => {
    await render({ progressPct: 80, ultra: true })
    tick(1000)
    tick(1100)
    // Ultra：蓝色叠加提饱和
    expect(ctx.calls.some((c) => c.startsWith('fillRect'))).toBe(true)
    // 进度收缩：越界星点被回收，超额散点被清退
    await render({ progressPct: 20 })
    tick(2000)
    tick(2100)
    expect(ctx.calls.some((c) => c.startsWith('clip'))).toBe(true)
  })
})

function canvasWidth(): number {
  const canvas = document.querySelector('canvas')
  return canvas ? canvas.width : 0
}
