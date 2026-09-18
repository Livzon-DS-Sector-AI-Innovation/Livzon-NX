'use client'

/**
 * 本月发酵进度条粒子层（对齐 Codex 推理深度滑块的真实动效）：
 * - 生成：粒子在轨道最右端（进度点内侧）源源不断生成，间距随机
 *   2~40px（达成率 ≥ 100% 时加密为 1~20px）；
 * - 运动：所有粒子以同一基准速度从右向左匀速流动，叠加每颗粒子随机的
 *   微小上下晃动（正弦扰动，幅度/相位/方向随机），如流体中微粒错落漂浮，
 *   不会排成整齐横线；
 * - 生命周期：向左穿越已完成段，到左缘渐隐回收；进度收缩时越界粒子即回收；
 * - 变化光泽：进度变化时紫色微光从进度点向左漫开约 1.2s 后消散。
 * 纯装饰层：绝对定位 Canvas，不拦截鼠标事件，不改变进度条逻辑。
 */

import { useEffect, useRef } from 'react'

interface ProgressParticlesProps {
  /** 进度点位置（0-100，轨道宽度百分比） */
  progressPct: number
  /** 产能达成率 ≥ 100%（最高密度模式） */
  ultra: boolean
}

interface Particle {
  /** 当前横向位置（px） */
  x: number
  /** 纵向基准位置（px），叠加正弦晃动后为实际 y */
  baseY: number
  /** 上下晃动幅度（px，随机——有的偏上、有的偏下、有的几乎不动） */
  swayAmp: number
  /** 晃动频率 */
  swayFreq: number
  /** 晃动相位（随机化错落感） */
  swayPhase: number
  r: number
  baseAlpha: number
  age: number
  breathe: number
}

const rand = (min: number, max: number) => min + Math.random() * (max - min)

/** 基准流速（px/s）：所有粒子一致的向左匀速 */
const FLOW_SPEED = 320
/** 相邻粒子的目标间距（px，随机）：普通档 / ultra 档 */
const GAP_RANGE = { min: 2, max: 40 } as const
const ULTRA_GAP_RANGE = { min: 1, max: 20 } as const

export default function ProgressParticles({
  progressPct,
  ultra,
}: ProgressParticlesProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  const pctRef = useRef<number | null>(null)
  const anim = useRef({
    particles: [] as Particle[],
    width: 0,
    height: 0,
    pct: 0,
    ultra: false,
    washUntil: 0,
    last: 0,
    /** 距上次生成已流过的距离（px） */
    sinceSpawn: 0,
    /** 下一次生成的目标间距（px，随机） */
    nextGap: 42,
  })

  // 进度变化 → 触发 1.2s 紫色微光回渗
  useEffect(() => {
    const d = anim.current
    const first = pctRef.current === null
    const changed = !first && pctRef.current !== progressPct
    pctRef.current = progressPct
    d.pct = progressPct
    d.ultra = ultra
    if (changed) d.washUntil = performance.now() + 1200
  }, [progressPct, ultra])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const d = anim.current

    const resize = () => {
      const parent = canvas.parentElement
      if (!parent) return
      const rect = parent.getBoundingClientRect()
      const dpr = window.devicePixelRatio || 1
      d.width = rect.width
      d.height = rect.height
      canvas.width = Math.max(1, Math.round(rect.width * dpr))
      canvas.height = Math.max(1, Math.round(rect.height * dpr))
      canvas.style.width = `${rect.width}px`
      canvas.style.height = `${rect.height}px`
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }
    resize()
    let ro: ResizeObserver | undefined
    if (typeof ResizeObserver !== 'undefined') {
      ro = new ResizeObserver(resize)
      if (canvas.parentElement) ro.observe(canvas.parentElement)
    }

    const tipX = () => (d.pct / 100) * d.width

    const spawn = () => {
      const tip = tipX()
      if (tip <= 8) return
      d.particles.push({
        x: tip - 2,
        baseY: rand(4, d.height - 4),
        swayAmp: rand(0.3, 2.2),
        swayFreq: rand(2, 6),
        swayPhase: rand(0, Math.PI * 2),
        r: rand(0.7, 1.8),
        baseAlpha: rand(0.3, 0.8),
        age: 0,
        breathe: rand(1.2, 3),
      })
    }

    let raf = 0
    const tick = (now: number) => {
      const dt = d.last ? Math.min(0.05, (now - d.last) / 1000) : 0.016
      d.last = now
      const tip = tipX()

      // 源源不断在最右端生成：流过随机目标间距（30~55px，ultra 25~31px）
      // 即生成一颗，间距天然随机、不排成等距横列
      d.sinceSpawn += FLOW_SPEED * dt
      if (d.sinceSpawn >= d.nextGap) {
        d.sinceSpawn = 0
        const gap = d.ultra ? ULTRA_GAP_RANGE : GAP_RANGE
        d.nextGap = rand(gap.min, gap.max)
        spawn()
      }

      // 运动：向左匀速流动；越出进度点或流出左缘即回收
      for (let i = d.particles.length - 1; i >= 0; i--) {
        const p = d.particles[i]
        p.age += dt
        p.x -= FLOW_SPEED * dt
        if (p.x < 2 || p.x > tip - 1) d.particles.splice(i, 1)
      }

      // 绘制：裁剪到「已完成」段内，粒子不越过进度点
      ctx.clearRect(0, 0, d.width, d.height)
      if (tip > 1) {
        ctx.save()
        ctx.beginPath()
        ctx.rect(0, 0, tip, d.height)
        ctx.clip()
        if (d.ultra) {
          // Ultra：蓝色叠加提饱和
          ctx.fillStyle = 'rgba(88, 150, 230, 0.16)'
          ctx.fillRect(0, 0, tip, d.height)
        }

        // 变化光泽：紫色微光自进度点向左漫开，随时间消散
        if (now < d.washUntil) {
          const k = Math.max(0, (d.washUntil - now) / 1200)
          const grad = ctx.createLinearGradient(0, 0, tip, 0)
          grad.addColorStop(0, 'rgba(150, 105, 235, 0)')
          grad.addColorStop(1, `rgba(150, 105, 235, ${0.22 * k})`)
          ctx.fillStyle = grad
          ctx.fillRect(0, 0, tip, d.height)
        }

        for (const p of d.particles) {
          const y =
            p.baseY + Math.sin(p.age * p.swayFreq + p.swayPhase) * p.swayAmp
          // 刚生成 0.2s 内快速浮现；接近左缘 40px 渐隐
          const fadeIn = Math.min(1, p.age / 0.2)
          const fadeOut = Math.min(1, Math.max(0, (p.x - 2) / 40))
          const breathe = 0.8 + 0.2 * Math.sin((now / 1000) * p.breathe)
          ctx.globalAlpha = Math.max(
            0,
            Math.min(1, p.baseAlpha * fadeIn * fadeOut * breathe),
          )
          ctx.beginPath()
          ctx.arc(p.x, y, p.r, 0, Math.PI * 2)
          ctx.fillStyle = '#fff'
          ctx.fill()
        }
        ctx.globalAlpha = 1
        ctx.restore()
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)

    return () => {
      cancelAnimationFrame(raf)
      ro?.disconnect()
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      data-testid="progress-particles"
      className="pointer-events-none absolute inset-0"
      style={{ zIndex: 2 }}
    />
  )
}
