'use client'

import { useEffect, useRef } from 'react'

import styles from './IdentityBubble.module.css'

interface FieldPoint {
  x: number
  y: number
  vx: number
  vy: number
  radius: number
  alpha: number
  tone: number
}

const POINT_COUNT = 58
const CONNECTION_DISTANCE = 155

export function LoginAtmosphere() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const context = canvas.getContext('2d')
    if (!context) return
    const canvasElement: HTMLCanvasElement = canvas
    const drawingContext: CanvasRenderingContext2D = context

    const reducedMotion = window.matchMedia(
      '(prefers-reduced-motion: reduce)',
    ).matches
    const pointer = { x: -1000, y: -1000 }
    let width = 0
    let height = 0
    let animationFrame = 0
    let points: FieldPoint[] = []

    function createPoints() {
      points = Array.from({ length: POINT_COUNT }, (_, index) => {
        const angle = (index / POINT_COUNT) * Math.PI * 2
        const orbit = 0.16 + ((index * 47) % 100) / 170
        return {
          x: width * (0.5 + Math.cos(angle) * orbit),
          y: height * (0.5 + Math.sin(angle) * orbit * 0.72),
          vx: ((index * 29) % 17 - 8) * 0.006,
          vy: ((index * 41) % 19 - 9) * 0.005,
          radius: 0.75 + ((index * 13) % 8) * 0.14,
          alpha: 0.18 + ((index * 31) % 10) * 0.028,
          tone: index % 3,
        }
      })
    }

    function resize() {
      const bounds = canvasElement.getBoundingClientRect()
      const pixelRatio = Math.min(window.devicePixelRatio || 1, 1.5)
      width = bounds.width
      height = bounds.height
      canvasElement.width = Math.round(width * pixelRatio)
      canvasElement.height = Math.round(height * pixelRatio)
      drawingContext.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0)
      createPoints()
    }

    function draw() {
      drawingContext.clearRect(0, 0, width, height)

      for (let index = 0; index < points.length; index += 1) {
        const point = points[index]

        if (!reducedMotion) {
          point.x += point.vx
          point.y += point.vy

          const pointerDistance = Math.hypot(
            point.x - pointer.x,
            point.y - pointer.y,
          )
          if (pointerDistance < 190) {
            const pull = (190 - pointerDistance) / 190
            point.x += (pointer.x - point.x) * pull * 0.0024
            point.y += (pointer.y - point.y) * pull * 0.0024
          }

          if (point.x < -20) point.x = width + 20
          if (point.x > width + 20) point.x = -20
          if (point.y < -20) point.y = height + 20
          if (point.y > height + 20) point.y = -20
        }

        for (
          let targetIndex = index + 1;
          targetIndex < points.length;
          targetIndex += 1
        ) {
          const target = points[targetIndex]
          const distance = Math.hypot(point.x - target.x, point.y - target.y)
          if (distance > CONNECTION_DISTANCE) continue

          const opacity = (1 - distance / CONNECTION_DISTANCE) * 0.105
          const gradient = drawingContext.createLinearGradient(
            point.x,
            point.y,
            target.x,
            target.y,
          )
          gradient.addColorStop(0, `rgba(51, 112, 255, ${opacity})`)
          gradient.addColorStop(1, `rgba(69, 176, 255, ${opacity * 0.72})`)
          drawingContext.beginPath()
          drawingContext.moveTo(point.x, point.y)
          drawingContext.lineTo(target.x, target.y)
          drawingContext.strokeStyle = gradient
          drawingContext.lineWidth = 0.65
          drawingContext.stroke()
        }

        const colors = [
          `rgba(51, 112, 255, ${point.alpha})`,
          `rgba(69, 176, 255, ${point.alpha * 0.84})`,
          `rgba(133, 202, 255, ${point.alpha * 0.9})`,
        ]
        drawingContext.beginPath()
        drawingContext.arc(point.x, point.y, point.radius, 0, Math.PI * 2)
        drawingContext.fillStyle = colors[point.tone]
        drawingContext.fill()
      }

      if (!reducedMotion) {
        animationFrame = window.requestAnimationFrame(draw)
      }
    }

    function handlePointerMove(event: PointerEvent) {
      pointer.x = event.clientX
      pointer.y = event.clientY
    }

    function handlePointerLeave() {
      pointer.x = -1000
      pointer.y = -1000
    }

    const resizeObserver = new ResizeObserver(resize)
    resizeObserver.observe(canvasElement)
    window.addEventListener('pointermove', handlePointerMove, { passive: true })
    document.addEventListener('mouseleave', handlePointerLeave)
    resize()
    draw()

    return () => {
      window.cancelAnimationFrame(animationFrame)
      resizeObserver.disconnect()
      window.removeEventListener('pointermove', handlePointerMove)
      document.removeEventListener('mouseleave', handlePointerLeave)
    }
  }, [])

  return (
    <div className={styles.atmosphere} aria-hidden="true">
      <canvas ref={canvasRef} className={styles.atmosphereCanvas} />
      <span className={`${styles.mist} ${styles.mistBlue}`} />
      <span className={`${styles.mist} ${styles.mistCyan}`} />
      <span className={`${styles.mist} ${styles.mistIce}`} />
      <span className={styles.centerAura} />
    </div>
  )
}
