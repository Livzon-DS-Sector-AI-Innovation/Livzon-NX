'use client'
// 通用工段仪表盘：统计卡片 + 月份选择 + 趋势图（警戒线可配置）

import { useMemo, useState } from 'react'
import { Button, Card, InputNumber, Modal, Row, Col, Select, Space, Typography, Statistic, App } from 'antd'
import { SettingOutlined } from '@ant-design/icons'
import ReactECharts from '@/components/shared/ThemedEChart'
import { useChartThresholds, type ChartLineConfig } from './chart-thresholds'

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
  /** 页面范围键：传入后显示警戒线配置入口，线值后端持久化、全平台共享 */
  scopeKey?: string
  /** 可配置警戒线的图表（key 对应 charts 项），缺省线值取图表自带 markLine */
  lineConfigs?: ChartLineConfig[]
}

export default function Dashboard({ title, data, dateField, cards, charts, month: externalMonth, scopeKey, lineConfigs }: DashboardProps) {
  const { message } = App.useApp()
  const hasExternalMonth = externalMonth !== undefined
  const [internalMonth, setInternalMonth] = useState<string>('全部')
  const [selectedChart, setSelectedChart] = useState<string>(charts[0]?.key || '')
  const [lineModalOpen, setLineModalOpen] = useState(false)
  const [lineDraft, setLineDraft] = useState<Record<string, number | undefined>>({})
  const [lineSaving, setLineSaving] = useState(false)
  const { values: lineValues, save: saveLine } = useChartThresholds(
    scopeKey && lineConfigs?.length ? scopeKey : undefined,
  )

  // 可配置图表的线值：后端配置优先，缺省回落图表自带 markLine
  const lineFor = (cfg: ChartDef): number | undefined => {
    const conf = lineConfigs?.find((c) => c.key === cfg.key)
    if (!conf) return cfg.markLine
    const v = lineValues[cfg.key]
    return v != null ? v : cfg.markLine
  }

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
        markLine: lineFor(cfg) != null ? {
          silent: true, data: [{ yAxis: lineFor(cfg), label: { formatter: `标准: ${lineFor(cfg)}`, fontSize: 10 }, lineStyle: { color: '#f5222d', type: 'dashed' } }],
        } : undefined,
        markPoint: lineFor(cfg) != null ? {
          data: vals.map((v: number | null, i: number) => {
            if (v == null || lineFor(cfg) == null) return null
            const over = cfg.markLineAbove ? v > lineFor(cfg)! : v < lineFor(cfg)!
            return over ? { name: String(names[i]), coord: [i, v], value: v, itemStyle: { color: '#f5222d' }, symbolSize: 8 } : null
          }).filter(Boolean).slice(0, 15),
        } : undefined,
      }],
      grid: { left: 55, right: 20, top: 40, bottom: 60 },
    }
  }, [filtered, selectedChart, charts, lineValues, lineConfigs])

  const openLineModal = () => {
    const draft: Record<string, number | undefined> = {}
    for (const conf of lineConfigs ?? []) {
      draft[conf.key] = lineValues[conf.key] ??
        charts.find((c) => c.key === conf.key)?.markLine
    }
    setLineDraft(draft)
    setLineModalOpen(true)
  }

  const handleLineSave = async () => {
    if (!scopeKey) return
    setLineSaving(true)
    try {
      for (const conf of lineConfigs ?? []) {
        const v = lineDraft[conf.key]
        if (v == null) continue
        const ok = await saveLine(conf.key, v)
        if (!ok) { message.error(`「${conf.label}」保存失败`); return }
      }
      message.success('警戒线已保存，全平台生效')
      setLineModalOpen(false)
    } finally {
      setLineSaving(false)
    }
  }

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
        <Row className="mb-2"><Col>
          <Text strong>趋势图：</Text>
          <Select aria-label={`${title}趋势指标`} size="small" value={selectedChart} onChange={setSelectedChart} style={{ width: 150, marginLeft: 8 }}
            options={charts.map(c => ({ value: c.key, label: c.label }))} />
          {scopeKey && lineConfigs?.length ? (
            <Button size="small" icon={<SettingOutlined />} style={{ marginLeft: 8 }} onClick={openLineModal}>
              警戒线
            </Button>
          ) : null}
        </Col></Row>
        <ReactECharts option={chartOption} style={{ height: 260 }} />
      </>}
      <Modal title="警戒线配置（全平台共享）" open={lineModalOpen} onOk={handleLineSave}
        onCancel={() => setLineModalOpen(false)} confirmLoading={lineSaving}
        okText="保存" cancelText="取消" width={420}>
        {(lineConfigs ?? []).map((conf) => (
          <div key={conf.key} style={{ display: 'flex', alignItems: 'center', marginBottom: 12 }}>
            <Text style={{ flex: 1 }}>{conf.label}{conf.unit ? `（${conf.unit}）` : ''}</Text>
            <InputNumber
              value={lineDraft[conf.key]}
              onChange={(v) => setLineDraft((prev) => ({ ...prev, [conf.key]: v ?? undefined }))}
              style={{ width: 120 }}
            />
          </div>
        ))}
        <Text type="secondary">保存后趋势图红线与相关卡片红绿判断立即按新值生效，对所有用户生效。</Text>
      </Modal>
    </Card>
  )
}
