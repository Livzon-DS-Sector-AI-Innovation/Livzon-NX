'use client'

import { Card, Collapse, Empty, Typography } from 'antd'
import dayjs from 'dayjs'
import type { EChartsOption } from 'echarts'
import ThemedEChart from '@/components/shared/ThemedEChart'
import { CATEGORY_LABELS, type Report } from '@/lib/api/energy-ledger'
import styles from './EnergyWorkspace.module.css'

function key(row: Report['totals'][number]) {
  return `${row.category}/${row.unit}/${row.quantity_kind}/${row.temperature}`
}

const numberFormat = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 8 })

export function EnergyUsageTrends({ report }: { report: Report }) {
  const count = dayjs(report.end_date).diff(dayjs(report.start_date), 'day') + 1
  const dates = Array.from({ length: count }, (_, index) => dayjs(report.start_date).add(index, 'day').format('YYYY-MM-DD'))

  return <>
    <div className={styles.trendGrid}>
      {report.totals.map(total => {
        const name = `${CATEGORY_LABELS[total.category]} ${total.temperature}`.trim()
        const peers = report.totals.filter(row => row.category === total.category && row.temperature === total.temperature)
        const title = peers.length > 1 ? `${name} · 口径 ${peers.indexOf(total) + 1}` : name
        const unit = total.unit
        const rows = new Map((report.trend ?? []).filter(row => key(row) === key(total)).map(row => [row.usage_date, row]))
        const values = dates.map(date => {
          const row = rows.get(date)
          return row && row.expected_count > 0 && row.available_count === row.expected_count && row.value !== null && Number.isFinite(Number(row.value)) ? Number(row.value) : null
        })
        const validCount = values.filter(value => value !== null).length
        const option: EChartsOption = {
          aria: { enabled: true },
          grid: { left: 16, right: 24, top: 48, bottom: 24, containLabel: true },
          legend: { top: 0, left: 0, data: ['日用量'] },
          tooltip: {
            trigger: 'axis', confine: true, renderMode: 'richText',
            formatter: params => {
              const point = Array.isArray(params) ? params[0] : params
              const index = point?.dataIndex
              if (index === undefined || index < 0 || index >= dates.length) return ''
              const value = values[index]
              return `${dates[index]}\n${title}\n${value === null ? '数据缺失或不完整' : `日用量：${numberFormat.format(value)} ${unit}`}`
            },
          },
          xAxis: { type: 'category', boundaryGap: false, data: dates, axisTick: { show: false }, axisLabel: { hideOverlap: true, formatter: (value: string) => dayjs(value).format('M/D') } },
          yAxis: { type: 'value', name: unit, splitNumber: 4, axisLabel: { formatter: (value: number) => Math.abs(value) >= 10000 ? `${numberFormat.format(value / 10000)}万` : numberFormat.format(value) } },
          series: [{ name: '日用量', type: 'line', smooth: false, connectNulls: false, showSymbol: true, symbol: 'circle', symbolSize: 6, lineStyle: { width: 2 }, data: values }],
        }
        return <Card key={key(total)} className={styles.trendCard} aria-label={`${title}用量趋势`}>
          <div className={styles.overviewHeading}>
            <Typography.Title level={5}>{title}用量趋势</Typography.Title>
            <Typography.Text type={validCount === count ? 'success' : 'warning'}>有效 {validCount} / {count} 天</Typography.Text>
          </div>
          <Typography.Text type="secondary">{report.start_date} 至 {report.end_date} · 单位：{unit}</Typography.Text>
          {validCount > 0 ? <ThemedEChart option={option} style={{ height: 300, width: '100%' }} /> : <div className={styles.trendEmpty}><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="所选期间暂无完整日用量" /></div>}
          <Collapse className={styles.trendValues} ghost size="small" items={[{
            key: 'daily-values', label: '查看每日数值',
            children: <dl>{dates.map((date, index) => <div key={date}><dt>{date}</dt><dd>{values[index] === null ? '数据缺失或不完整' : `${numberFormat.format(values[index])} ${unit}`}</dd></div>)}</dl>,
          }]} />
        </Card>
      })}
    </div>
  </>
}
