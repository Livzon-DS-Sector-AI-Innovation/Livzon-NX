'use client'
// 通用工段仪表盘：统计卡片 + 月份选择 + 趋势图

import { useMemo, useState } from 'react'
import { Card, Row, Col, Select, Space, Typography, Statistic } from 'antd'
import ReactECharts from 'echarts-for-react'

const { Text } = Typography

interface ChartDef {
  key: string
  label: string
  title: string
  unit: string
  color: string
  field: string
  markLine?: number
  markLineAbove?: boolean
}

interface DashboardProps {
  title: string
  data: any[]
  dateField: string
  cards: {
    title: string; value: (d: any, filtered: any[]) => number | string | null
    suffix: string; precision?: number; color?: (v: number) => string
  }[]
  charts: ChartDef[]
  month?: number  // 0=全部, 1-12=按月, 未传则内部管理
}

export default function Dashboard({ title, data, dateField, cards, charts, month: externalMonth }: DashboardProps) {
  const hasExternalMonth = externalMonth !== undefined
  const [internalMonth, setInternalMonth] = useState<string>('全部')
  const [selectedChart, setSelectedChart] = useState<string>(charts[0]?.key || '')

  const months = useMemo(() => {
    const s = new Set<string>()
    for (const item of data) {
      const d = item[dateField]
      if (d) s.add(d.substring(0, 7))
    }
    return ['全部', ...Array.from(s).sort()]
  }, [data, dateField])

  const filtered = useMemo(() => {
    if (hasExternalMonth) {
      if (externalMonth === 0) return data
      return data.filter(item => {
        const d = item[dateField || '']
        if (!d) return false
        const m = parseInt(d.substring(5, 7))
        return m === externalMonth
      })
    }
    if (internalMonth === '全部') return data
    return data.filter(item => item[dateField || '']?.startsWith(internalMonth))
  }, [data, internalMonth, dateField, hasExternalMonth, externalMonth])

  const chartOption = useMemo(() => {
    const cfg = charts.find(c => c.key === selectedChart)
    if (!cfg) return {}
    const names: string[] = []; const vals: (number | null)[] = []
    for (const item of filtered) {
      names.push(item.batch_no || item._label || '')
      vals.push(item[cfg.field] ?? null)
    }
    return {
      tooltip: { trigger: 'axis' },
      title: { text: cfg.title, left: 'center', textStyle: { fontSize: 14 } },
      xAxis: { type: 'category', data: names, axisLabel: { fontSize: 9, rotate: 45 } },
      yAxis: { type: 'value', name: cfg.unit, axisLabel: { fontSize: 10 } },
      series: [{
        type: 'line', name: cfg.title, data: vals, itemStyle: { color: cfg.color },
        markLine: cfg.markLine != null ? {
          silent: true, data: [{ yAxis: cfg.markLine, label: { formatter: `标准: ${cfg.markLine}`, fontSize: 10 }, lineStyle: { color: '#f5222d', type: 'dashed' } }],
        } : undefined,
        markPoint: cfg.markLine != null ? {
          data: vals.map((v: number | null, i: number) => {
            if (v == null || cfg.markLine == null) return null
            const over = cfg.markLineAbove ? v > cfg.markLine : v < cfg.markLine
            return over ? { name: String(names[i]), coord: [i, v], value: v, itemStyle: { color: '#f5222d' }, symbolSize: 8 } : null
          }).filter(Boolean).slice(0, 15),
        } : undefined,
      }],
      grid: { left: 55, right: 20, top: 40, bottom: 60 },
    }
  }, [filtered, selectedChart, charts])

  return (
    <Card size="small" className="mb-4" title={
      <Space><Text strong style={{ fontSize: 14 }}>📊 {title}</Text>
        {!hasExternalMonth && (
          <Select size="small" value={internalMonth} onChange={setInternalMonth} style={{ width: 80 }}
            options={months.map(m => ({ value: m, label: m === '全部' ? '全部' : m.substring(5) + '月' }))} />
        )}
      </Space>
    }>
      <Row gutter={12} className="mb-3">
        {cards.map((c, i) => {
          const v = c.value(data, filtered)
          return (
            <Col key={i} flex="1">
              <Statistic title={c.title} value={v ?? undefined} suffix={c.suffix} precision={c.precision}
                styles={{ content: { fontSize: 16, color: c.color ? c.color(Number(v)) : undefined } }} />
            </Col>
          )
        })}
      </Row>
      {charts.length > 0 && <>
        <Row className="mb-2"><Col><Text strong>趋势图：</Text>
          <Select size="small" value={selectedChart} onChange={setSelectedChart} style={{ width: 150, marginLeft: 8 }}
            options={charts.map(c => ({ value: c.key, label: c.label }))} />
        </Col></Row>
        <ReactECharts option={chartOption} style={{ height: 260 }} />
      </>}
    </Card>
  )
}
