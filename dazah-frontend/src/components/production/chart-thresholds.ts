import { useCallback, useEffect, useState } from 'react'

/** 图表警戒线配置（后端持久化，全平台共享）。 */

export type ChartLineConfig = {
  key: string
  label: string
  unit?: string
}

export function useChartThresholds(scopeKey: string | undefined) {
  const [values, setValues] = useState<Record<string, number>>({})
  useEffect(() => {
    if (!scopeKey) return
    let cancelled = false
    fetch(
      `/api/v1/production/chart-thresholds?scope_key=${encodeURIComponent(scopeKey)}`,
    )
      .then((r) => r.json())
      .then((d) => {
        if (!cancelled && d.code === 200) setValues(d.data || {})
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [scopeKey])
  const save = useCallback(
    async (chartKey: string, threshold: number) => {
      if (!scopeKey) return false
      try {
        const res = await fetch('/api/v1/production/chart-thresholds', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            scope_key: scopeKey,
            chart_key: chartKey,
            threshold,
          }),
        })
        const d = await res.json()
        if (d.code !== 200) return false
        setValues((prev) => ({ ...prev, [chartKey]: threshold }))
        return true
      } catch {
        return false
      }
    },
    [scopeKey],
  )
  return { values, save }
}
