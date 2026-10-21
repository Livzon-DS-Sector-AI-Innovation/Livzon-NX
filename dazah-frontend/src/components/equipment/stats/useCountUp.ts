'use client'

import { useEffect, useRef, useState } from 'react'

// ============================================================
// 工具：数字动画 Hook
// ============================================================
export function useCountUp(target: number, duration = 1200) {
  const [value, setValue] = useState(target)
  const raf = useRef<number>(0)
  const startTime = useRef(0)
  const fromValue = useRef(value)
  const prevTarget = useRef(target)

  useEffect(() => {
    if (prevTarget.current === target) return
    prevTarget.current = target
    fromValue.current = value
    startTime.current = 0
    let active = true

    const animate = (timestamp: number) => {
      if (!startTime.current) startTime.current = timestamp
      const elapsed = timestamp - startTime.current
      const progress = Math.min(elapsed / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      const current = Math.round(fromValue.current + (target - fromValue.current) * eased)
      if (active) setValue(current)
      if (progress < 1) {
        raf.current = requestAnimationFrame(animate)
      }
    }

    raf.current = requestAnimationFrame(animate)
    return () => { active = false; cancelAnimationFrame(raf.current) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, duration])

  return value
}
