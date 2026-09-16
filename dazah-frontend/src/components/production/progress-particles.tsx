'use client'

/**
 * 本月批次进度条粒子脉冲层（对齐 Codex 推理强度滑块的粒子动效）：
 * - 静态：深蓝「已完成」段内散落半透明白色思考粒子，缓慢闪烁；
 * - 进度变化：粒子从箭头底边位置生成（已完成矩形右缘 −17px = 进度点
 *   左侧 34px）、只向左流动漂移并淡出（箭头盖在粒子上层，露出底缘
 *   左侧即「从三角中喷出」），涨幅越大越密越快，
 *   粒子被进度点阻挡、不会进入右侧未完成区域；
 * - 进度落定：进度点触发一圈冲击波，粒子短暂爆发后回落稳定；
 * - 产能达成率 ≥ 100%：粒子密度翻倍 + 持续微光扫光 + 蓝色叠加提饱和。
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
  kind: 'dot' | 'flow'
  x: number
  y: number
  r: number
  alpha: number
  baseAlpha: number
  vx: number
  vy: number
  age: number
  life: number
  twinkle: number
}

interface Wave {
  x: number
  r: number
  alpha: number
}

const rand = (min: number, max: number) => min + Math.random() * (max - min)

/** 粒子发射区间（px）：进度点左侧 34px，与 batch-progress-bar 箭头横向跨度一致 */
const EMIT_SPAN_PX = 34

export default function ProgressParticles({
  progressPct,
  ultra,
}: ProgressParticlesProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  const pctRef = useRef<number | null>(null)
  const anim = useRef({
    particles: [] as Particle[],
    waves: [] as Wave[],
    width: 0,
    height: 0,
    pct: 0,
    ultra: false,
    flowUntil: 0,
    shockAt: 0,
    last: 0,
    sweep: 0,
  })

  // 进度变化 → 触发 1.2s 粒子流动，随后冲击波（落定吸附）
  useEffect(() => {
    const d = anim.current
    const first = pctRef.current === null
    const changed = !first && pctRef.current !== progressPct
    pctRef.current = progressPct
    d.pct = progressPct
    d.ultra = ultra
    if (changed) {
      const now = performance.now()
      d.flowUntil = now + 1200
      d.shockAt = now + 1200
    }
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

    const spawnDot = () => {
      const tip = tipX()
      if (tip <= 4) return
      d.particles.push({
        kind: 'dot',
        x: rand(2, tip - 2),
        y: rand(3, d.height - 3),
        r: rand(0.8, 1.9),
        alpha: 0,
        baseAlpha: rand(0.22, 0.5),
        vx: 0,
        vy: 0,
        age: 0,
        life: Number.POSITIVE_INFINITY,
        twinkle: rand(0.5, 2.2),
      })
    }

    const spawnFlow = (count: number) => {
      const tip = tipX()
      if (tip <= 4) return
      for (let i = 0; i < count; i++) {
        d.particles.push({
          kind: 'flow',
          // 从箭头底边位置发出（进度点左侧 34px = 已完成矩形右缘 −17px），
          // 向左漂移；箭头盖在粒子上层，一露出底缘左侧即「从三角喷出」
          x: Math.max(1, tip - EMIT_SPAN_PX),
          y: rand(3, d.height - 3),
          r: rand(0.7, 1.7),
          alpha: 0,
          baseAlpha: rand(0.35, 0.75),
          vx: -rand(16, d.ultra ? 96 : 64),
          vy: rand(-6, 6),
          age: 0,
          life: rand(0.8, 1.9),
          twinkle: 0,
        })
      }
    }

    let raf = 0
    const tick = (now: number) => {
      const dt = d.last ? Math.min(0.05, (now - d.last) / 1000) : 0.016
      d.last = now
      const tip = tipX()
      const flowOn = now < d.flowUntil

      // 拖动（进度变化）期间：持续生成流动粒子
      if (flowOn) {
        spawnFlow(Math.ceil(dt * (d.ultra ? 90 : 55)))
      } else if (d.shockAt && now >= d.shockAt) {
        // 落定吸附：冲击波 + 粒子短暂爆发
        d.waves.push({ x: tip, r: 2, alpha: 0.55 })
        spawnFlow(d.ultra ? 26 : 16)
        d.shockAt = 0
      }

      // 维持静态散点密度（Ultra 翻倍）
      const target = Math.round(
        Math.min(40, Math.max(4, tip / 30)) * (d.ultra ? 1.8 : 1),
      )
      const dots = d.particles.filter((p) => p.kind === 'dot').length
      if (dots < target) spawnDot()
      else if (dots > target + 6) {
        const idx = d.particles.findIndex((p) => p.kind === 'dot')
        if (idx > -1) d.particles.splice(idx, 1)
      }

      // 物理更新与回收
      for (let i = d.particles.length - 1; i >= 0; i--) {
        const p = d.particles[i]
        p.age += dt
        if (p.kind === 'flow') {
          p.x += p.vx * dt
          p.y += p.vy * dt
          p.alpha = p.baseAlpha * Math.max(0, 1 - p.age / p.life)
          if (p.alpha <= 0.02 || p.age >= p.life || p.x > tip - 1) {
            d.particles.splice(i, 1)
            continue
          }
        } else {
          p.alpha = p.baseAlpha * (0.62 + 0.38 * Math.sin((now / 1000) * p.twinkle))
          // 进度收缩时把越界散点拉回已完成段
          if (p.x > tip - 2) p.x = rand(2, Math.max(4, tip - 2))
        }
      }

      // 冲击波扩散
      for (let i = d.waves.length - 1; i >= 0; i--) {
        const w = d.waves[i]
        w.r += dt * 90
        w.alpha -= dt * 0.9
        if (w.alpha <= 0) d.waves.splice(i, 1)
      }

      // 绘制：裁剪到「已完成」段内，粒子不越过进度点
      ctx.clearRect(0, 0, d.width, d.height)
      if (tip > 1) {
        ctx.save()
        ctx.beginPath()
        ctx.rect(0, 0, tip, d.height)
        ctx.clip()
        if (d.ultra) {
          // Ultra：蓝色叠加提饱和 + 持续微光扫光
          ctx.fillStyle = 'rgba(88, 150, 230, 0.16)'
          ctx.fillRect(0, 0, tip, d.height)
          d.sweep = (d.sweep + dt / 2.6) % 1
          const sx = d.sweep * tip
          const grad = ctx.createLinearGradient(sx - 45, 0, sx + 45, 0)
          grad.addColorStop(0, 'rgba(255,255,255,0)')
          grad.addColorStop(0.5, 'rgba(255,255,255,0.14)')
          grad.addColorStop(1, 'rgba(255,255,255,0)')
          ctx.fillStyle = grad
          ctx.fillRect(sx - 45, 0, 90, d.height)
        }
        for (const p of d.particles) {
          ctx.globalAlpha = Math.max(0, Math.min(1, p.alpha))
          ctx.beginPath()
          ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
          ctx.fillStyle = '#fff'
          ctx.fill()
        }
        ctx.globalAlpha = 1
        for (const w of d.waves) {
          ctx.globalAlpha = Math.max(0, w.alpha)
          ctx.strokeStyle = '#fff'
          ctx.lineWidth = 1.5
          ctx.beginPath()
          ctx.arc(w.x, d.height / 2, w.r, -Math.PI / 2, Math.PI / 2)
          ctx.stroke()
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
