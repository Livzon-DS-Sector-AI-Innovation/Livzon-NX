/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import ProgressParticles from './progress-particles'

type Ctx = Record<string, unknown> & { calls: string[] }

function makeCtx(): Ctx {
  const ctx: Ctx = { calls: [] }
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
  ctx.arc = record('arc')
  ctx.fill = record('fill')
  ctx.stroke = record('stroke')
  ctx.restore = record('restore')
  ctx.createLinearGradient = () => ({ addColorStop: () => undefined })
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

  it('renders canvas, resizes, spawns static dots and draws them', async () => {
    await render()
    expect(container.querySelector('canvas')).toBeTruthy()
    // resize：以父元素尺寸 × dpr 设置画布
    expect(canvasWidth()).toBe(600)
    // 首帧：进度 60 → tip 360 → 静态散点维持密度并绘制
    tick(1000)
    expect(ctx.calls.some((c) => c.startsWith('clearRect'))).toBe(true)
    expect(ctx.calls.some((c) => c.startsWith('clip'))).toBe(true)
    expect(ctx.calls.some((c) => c.startsWith('arc'))).toBe(true)
    // 帧循环继续排队
    expect(rafQueue.length).toBe(1)
    // 进度不变时 effect 不触发流动窗口（无异常即可）
    await render({ progressPct: 60 })
  })

  it('spawning is skipped when tip is tiny and unmount cancels raf', async () => {
    await render({ progressPct: 0 })
    tick(1000)
    // tip ≤ 4：spawnDot 直接返回，不绘制裁剪区
    expect(ctx.calls.some((c) => c.startsWith('clip'))).toBe(false)
    act(() => root.unmount())
    expect(cancelled.length).toBeGreaterThan(0)
    // 卸载后无残留帧
    expect(rafQueue.length).toBe(0)
    // 标记 root 已卸载，afterEach 重复 unmount 安全
    root = createRoot(document.createElement('div'))
  })

  it('spawns flow particles on progress change then fires shock wave', async () => {
    await render({ progressPct: 60 })
    tick(1000)
    const before = ctx.calls.filter((c) => c.startsWith('fill')).length
    // 进度变化 → 1.2s 流动窗口
    await render({ progressPct: 75 })
    const now = performance.now()
    tick(now + 100)
    // 流动粒子被绘制（fill 次数增加）
    expect(ctx.calls.filter((c) => c.startsWith('fill')).length).toBeGreaterThan(
      before,
    )
    // 窗口结束 → 冲击波生成
    tick(now + 1400)
    tick(now + 1500)
    // 冲击波描边
    expect(ctx.calls.some((c) => c.startsWith('stroke'))).toBe(true)
    // 流动粒子寿命耗尽后被回收（不再触发异常即可）
    tick(now + 4000)
  })

  it('draws ultra sweep overlay and reflows dots on progress shrink', async () => {
    await render({ progressPct: 80, ultra: true })
    tick(1000)
    tick(1100)
    // Ultra：蓝色叠加 + 扫光渐变
    expect(ctx.calls.some((c) => c.startsWith('fillRect'))).toBe(true)
    // 进度收缩：越界散点被拉回已完成段，超额散点被回收
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
