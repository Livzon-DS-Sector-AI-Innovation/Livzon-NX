import { describe, expect, it } from 'vitest'
import { theme } from 'antd'
import { graphic } from 'echarts'
import { adaptChartAppearance } from './chartAppearance'
import { getAntdTheme } from './antd-theme'

describe('chart appearance', () => {
  it('adapts tooltip, axes and neutral labels without mutating business data or gradients', () => {
    const formatter = () => '批次数据'
    const data = [{ name: '#ffffff', value: 15, itemStyle: { color: '#e03131' } }]
    const gradient = new graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: '#ffffff' }, { offset: 1, color: '#5645d4' }])
    const option = {
      tooltip: { formatter, backgroundColor: '#ffffff', textStyle: { color: '#333' } },
      legend: { textStyle: { color: '#5a5f73' } },
      xAxis: { axisLabel: { color: '#8a8fa3' }, axisLine: { lineStyle: { color: '#e5e7eb' } } },
      series: [{ data, itemStyle: { color: gradient }, lineStyle: { color: '#e03131' } }],
    }
    const original = JSON.stringify(option)
    const result = adaptChartAppearance(option, 'dark')
    const token = theme.getDesignToken(getAntdTheme('dark'))
    expect(result).toMatchObject({
      backgroundColor: 'transparent',
      tooltip: { formatter, backgroundColor: token.colorBgElevated, textStyle: { color: token.colorText } },
      legend: { textStyle: { color: token.colorTextSecondary } },
      xAxis: { axisLabel: { color: token.colorTextSecondary }, axisLine: { lineStyle: { color: token.colorBorderSecondary } } },
      series: [{ data, itemStyle: { color: gradient }, lineStyle: { color: '#e03131' } }],
    })
    expect(JSON.stringify(option)).toBe(original)
    expect(adaptChartAppearance(option, 'light')).toBe(option)
  })

  it('resolves shared CSS tokens to actual colors for canvas in both modes', () => {
    for (const mode of ['light', 'dark'] as const) {
      const result = adaptChartAppearance({ textStyle: { color: 'var(--color-ink)' },
        xAxis: { splitLine: { lineStyle: { color: 'var(--color-hairline)' } } },
      }, mode)
      const token = theme.getDesignToken(getAntdTheme(mode))
      expect(result).toMatchObject({ textStyle: { color: token.colorText },
        xAxis: { splitLine: { lineStyle: { color: token.colorBorder } } },
      })
      expect(JSON.stringify(result)).not.toContain('var(')
    }
  })

  it('adapts multiple tooltip scopes and supports 3D options and callbacks', () => {
    const formatter = () => '三维响应'
    const option = { tooltip: [{ formatter }, { backgroundColor: '#fff' }],
      grid3D: { axisLabel: { color: '#333' } },
      series: [{ type: 'surface', data: [[1, 2, 3]], shading: 'realistic' }],
    }
    const result = adaptChartAppearance(option, 'dark')
    expect(result).toMatchObject({ tooltip: [{ formatter }, { backgroundColor: '#2b2b30' }],
      series: option.series, grid3D: { axisLabel: { color: '#eeedf1' } },
    })
  })
})
