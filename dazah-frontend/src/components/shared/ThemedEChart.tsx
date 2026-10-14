'use client'

import { useMemo, type Ref } from 'react'
import ReactECharts from 'echarts-for-react'
import type { EChartsReactProps } from 'echarts-for-react'
import { useAppearance } from '@/lib/useAppearance'
import { adaptChartAppearance } from '@/lib/chartAppearance'

type ThemedEChartProps = Omit<EChartsReactProps, 'option'> & {
  // ECharts extensions (including GL) also use this shared presentation boundary.
  option: unknown
  ref?: Ref<ReactECharts>
}

export default function ThemedEChart({ option, theme, ref, ...props }: ThemedEChartProps) {
  const { resolved } = useAppearance()
  const adapted = useMemo(() => option && typeof option === 'object'
    ? adaptChartAppearance(option, resolved) : {}, [option, resolved])
  return <ReactECharts {...props} ref={ref} option={adapted} theme={resolved === 'dark' ? 'dark' : theme} />
}
