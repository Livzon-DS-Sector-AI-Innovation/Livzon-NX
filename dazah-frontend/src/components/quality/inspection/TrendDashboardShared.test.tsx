/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import {
  TrendAiPanel,
  buildTrendOption,
  ruleTypeLabel,
} from './TrendDashboardShared'
import type { QualityInspectionDashboardChart } from '@/types/quality-inspection-dashboard'

function makeChart(overrides: Partial<QualityInspectionDashboardChart> = {}) {
  const base: QualityInspectionDashboardChart = {
    metric_key: '含量:97-103',
    metric_label: '含量（干品）',
    categories: ['B01', 'B02', 'B03'],
    actual_series: [97, 98, 99],
    mean_series: [98, 98, 98],
    upper_sigma_series: [100, 100, 100],
    lower_sigma_series: [96, 96, 96],
    spec_lines: [],
    points: [
      { batch_no: 'B01', value: 97 },
      { batch_no: 'B02', value: 98 },
      { batch_no: 'B03', value: 99 },
    ],
    summary: {
      sample_count: 3,
      mean: 98,
      std_dev: 0.8,
      upper_control_limit: 100,
      lower_control_limit: 96,
    },
    trend_anomalies: [],
    trend_ai: null,
    trend_ai_status: 'none',
    ...overrides,
  }
  return base
}

describe('buildTrendOption 趋势异常高亮', () => {
  it('无 AI 高亮时不产出 scatter 系列', () => {
    const option = buildTrendOption(makeChart(), false)
    const series = option.series as Array<{ name?: string; type?: string }>
    expect(series.some((s) => s.type === 'scatter')).toBe(false)
  })

  it('有 AI 高亮批次时追加对齐类目的 scatter 系列', () => {
    const chart = makeChart({
      trend_ai_status: 'completed',
      trend_ai: {
        summary: '上行',
        trend_reading: 'x',
        signals: [],
        outlook: { direction: 'up', batches_to_limit: null, risk: '' },
        recommendation: '',
        confidence: 'medium',
        highlight_batches: ['B02'],
        period: '2026-09',
      } as QualityInspectionDashboardChart['trend_ai'],
    })
    const option = buildTrendOption(chart, false)
    const scatter = (option.series as Array<{ type?: string; data?: unknown[]; name?: string }>).find(
      (s) => s.type === 'scatter'
    )
    expect(scatter).toBeTruthy()
    // 类目 [B01,B02,B03] 中仅 B02 有值，其余 null
    expect(scatter?.data).toEqual([null, 98, null])
    expect(scatter?.name).toBe('趋势异常批次')
  })

  it('深链 extraHighlight 批次也会高亮', () => {
    const option = buildTrendOption(makeChart(), false, ['B03'])
    const scatter = (option.series as Array<{ type?: string; data?: unknown[] }>).find(
      (s) => s.type === 'scatter'
    )
    expect(scatter?.data).toEqual([null, null, 99])
  })
})

describe('ruleTypeLabel', () => {
  it('映射已知规则并回退未知规则', () => {
    expect(ruleTypeLabel('month_level')).toBe('当月较历史抬升/下移')
    expect(ruleTypeLabel('month_slope')).toBe('当月内趋势')
    expect(ruleTypeLabel('slope_change')).toBe('斜率较历史变化')
    expect(ruleTypeLabel('month_over_month')).toBe('月度整体趋势')
    expect(ruleTypeLabel('mystery')).toBe('mystery')
  })
})

describe('TrendAiPanel', () => {
  let root: Root
  let container: HTMLElement

  beforeEach(() => {
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })
  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    document
      .querySelectorAll('.ant-message, .ant-modal-root')
      .forEach((n) => n.remove())
  })

  function render(chart: QualityInspectionDashboardChart) {
    act(() => root.render(<TrendAiPanel chart={chart} />))
  }

  it('无异常时提示未发现趋势异常', () => {
    render(makeChart())
    expect(container.textContent).toContain('未发现趋势异常')
  })

  it('有异常且 pending 时提示分析中', () => {
    render(
      makeChart({
        trend_ai_status: 'pending',
        trend_anomalies: [
          {
            rule_type: 'continuous_move',
            severity: 'medium',
            start_batch: 'B01',
            end_batch: 'B03',
            description: '连续 3 批上升',
            evidence: {},
            affected_batches: ['B03'],
          } as QualityInspectionDashboardChart['trend_anomalies'][number],
        ],
      })
    )
    expect(container.textContent).toContain('连续 3 批上升')
    expect(container.textContent).toContain('分析中')
  })

  it('completed 时展示 AI 研判与建议', () => {
    render(
      makeChart({
        trend_ai_status: 'completed',
        trend_anomalies: [
          {
            rule_type: 'slope_break',
            severity: 'high',
            start_batch: 'B01',
            end_batch: 'B03',
            description: '斜率突变',
            evidence: {},
            affected_batches: [],
          } as QualityInspectionDashboardChart['trend_anomalies'][number],
        ],
        trend_ai: {
          summary: '含量加速上行',
          trend_reading: '后半段斜率显著抬升',
          signals: [],
          outlook: { direction: 'up', batches_to_limit: 6, risk: '或越限' },
          recommendation: '建议加严监测',
          confidence: 'medium',
          highlight_batches: [],
          period: '2026-09',
          analyzed_at: '2026-09-08T08:00:00+00:00',
        } as QualityInspectionDashboardChart['trend_ai'],
      })
    )
    expect(container.textContent).toContain('含量加速上行')
    expect(container.textContent).toContain('约 6 批后逼近限度线')
    expect(container.textContent).toContain('建议加严监测')
  })
})
