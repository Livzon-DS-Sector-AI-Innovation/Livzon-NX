import type { EChartsOption, TooltipComponentOption } from 'echarts'
import { theme } from 'antd'
import { getAntdTheme } from './antd-theme'
import type { ColorMode } from './appearance'

const LIGHT_SURFACES = new Set(['#fff', '#ffffff', '#fafafa', '#fafaf9', '#f6f5f4', '#f8f9fb', '#f9fafb', '#f5f5f5'])
const DARK_TEXT = new Set(['#000', '#000000', '#111', '#111111', '#222', '#222222', '#333', '#333333', '#1a1a1a', '#37352f', '#0f172a', '#1f2937'])
const SECONDARY_TEXT = new Set(['#555', '#555555', '#666', '#666666', '#777', '#777777', '#888', '#888888', '#999', '#999999', '#5d5b54', '#787671', '#64748b', '#8a8fa3', '#5a5f73', '#6b7280', '#475569', 'rgba(0, 0, 0, 0.65)', 'rgba(0,0,0,0.65)'])
const LIGHT_BORDERS = new Set(['#ccc', '#cccccc', '#ddd', '#dddddd', '#eee', '#eeeeee', '#e5e3df', '#ede9e4', '#e5e7eb', '#e2e8f0', '#f0f0f0', '#f0eeec', '#e8e8e8', '#d9d9d9', '#e3e5ef', '#eef0f7'])
const COLOR_KEYS = new Set(['color', 'backgroundColor', 'borderColor', 'fill', 'stroke'])
const DATA_KEYS = new Set(['data', 'source', 'dataset', 'dimensions', 'encode', 'colorStops'])

/** Adapt presentation only; retain series data, semantic colors, callbacks and gradients. */
export function adaptChartAppearance(option: object, mode: ColorMode): object {
  const config = getAntdTheme(mode)
  const token = mode === 'dark' ? theme.getDesignToken(config) : config.token
  const variables: Record<string, string | undefined> = {
    '--color-ink': token?.colorText,
    '--color-slate': token?.colorTextSecondary,
    '--color-steel': token?.colorTextTertiary,
    '--color-hairline': token?.colorBorder,
    '--color-hairline-soft': token?.colorBorderSecondary,
    '--color-surface': token?.colorBgLayout,
    '--color-surface-soft': token?.colorBgContainer,
    '--color-canvas': token?.colorBgContainer,
    '--color-primary-soft': token?.colorPrimaryBg,
    '--color-info-soft': token?.colorInfoBg,
    '--color-success-soft': token?.colorSuccessBg,
    '--color-warning-soft': token?.colorWarningBg,
    '--color-error-soft': token?.colorErrorBg,
    '--color-warning': token?.colorWarning,
  }
  let changed = false
  function convert(value: unknown, key = '', path = ''): unknown {
    if (typeof value === 'string' && COLOR_KEYS.has(key)) {
      const variable = /^var\((--[\w-]+)(?:,[^)]+)?\)$/.exec(value)
      if (variable && variables[variable[1]]) {
        changed = true
        return variables[variable[1]]
      }
      if (mode === 'light') return value
      const color = value.toLowerCase()
      if (color === '#5645d4') return token?.colorPrimary
      if (color === '#4534b3') return token?.colorPrimaryActive
      if (key === 'backgroundColor' && LIGHT_SURFACES.has(color)) return token?.colorBgElevated
      if (path.includes('splitArea') && LIGHT_SURFACES.has(color)) return token?.colorBgContainer
      if (key === 'borderColor' || key === 'stroke' || path.includes('splitLine') || path.includes('axisLine')) {
        if (LIGHT_BORDERS.has(color) || DARK_TEXT.has(color) || SECONDARY_TEXT.has(color)) return token?.colorBorderSecondary
      }
      if (DARK_TEXT.has(color)) return token?.colorText
      if (SECONDARY_TEXT.has(color)) return token?.colorTextSecondary
      if (LIGHT_BORDERS.has(color)) return token?.colorBorderSecondary
      return value
    }
    if (Array.isArray(value)) return value.map((item) => convert(item, key, path))
    if (!value || typeof value !== 'object' || Object.getPrototypeOf(value) !== Object.prototype) return value
    return Object.fromEntries(Object.entries(value).map(([childKey, child]) => [childKey,
      DATA_KEYS.has(childKey) ? child : convert(child, childKey, `${path}.${childKey}`),
    ]))
  }
  // The structure and callbacks remain identical; only known presentation colors change.
  const adapted = convert(option) as EChartsOption
  if (mode === 'light') return changed ? adapted : option
  const tooltip = adapted.tooltip
  function adaptTooltip(value: TooltipComponentOption): TooltipComponentOption {
    return {
      ...value, backgroundColor: token?.colorBgElevated, borderColor: token?.colorBorder,
      textStyle: { ...value.textStyle, color: token?.colorText },
    }
  }
  // ECharts GL supplies its own dark axis defaults instead of inheriting textStyle.
  function presentation(value: unknown): Record<string, unknown> {
    return value && typeof value === 'object' && !Array.isArray(value)
      ? value as Record<string, unknown> : {}
  }
  function adapt3DAxes(value: unknown): unknown {
    if (Array.isArray(value)) return value.map(adapt3DAxes)
    if (!value || typeof value !== 'object') return value
    const axis = presentation(value)
    const axisLine = presentation(axis.axisLine)
    const splitLine = presentation(axis.splitLine)
    return {
      ...axis,
      nameTextStyle: { color: token?.colorTextSecondary, ...presentation(axis.nameTextStyle) },
      axisLabel: { color: token?.colorTextSecondary, ...presentation(axis.axisLabel) },
      axisLine: { ...axisLine, lineStyle: { color: token?.colorTextSecondary, ...presentation(axisLine.lineStyle) } },
      splitLine: { ...splitLine, lineStyle: { color: token?.colorBorderSecondary, ...presentation(splitLine.lineStyle) } },
    }
  }
  const extensions = adapted as EChartsOption & Record<string, unknown>
  const axes3D = Object.fromEntries(['grid3D', 'xAxis3D', 'yAxis3D', 'zAxis3D']
    .filter((key) => extensions[key] !== undefined)
    .map((key) => [key, adapt3DAxes(extensions[key])]))
  return {
    ...adapted,
    ...axes3D,
    backgroundColor: adapted.backgroundColor ?? 'transparent',
    textStyle: { ...adapted.textStyle, color: token?.colorText },
    ...(tooltip ? { tooltip: Array.isArray(tooltip) ? tooltip.map(adaptTooltip) : adaptTooltip(tooltip) } : {}),
  }
}
