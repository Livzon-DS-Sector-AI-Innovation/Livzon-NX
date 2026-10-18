'use client'

import { Card, Empty, Typography } from 'antd'
import type { EChartsOption } from 'echarts'
import ReactECharts from '@/components/shared/ThemedEChart'

import type { PageTableStats } from '@/lib/safety-page-tables'

const CHART_HEIGHT = 210

// 与应用主题一致的配色：主色紫、车间蓝、结论绿/橙
const PRIMARY_COLOR = '#5645d4'
const WORKSHOP_COLOR = '#2563eb'
const SUCCESS_COLOR = '#1aae39'
const WARNING_COLOR = '#dd5b00'
const NEUTRAL_COLOR = '#bfbfbf'
const SPLIT_LINE_COLOR = 'var(--color-hairline-soft)'
const AXIS_LINE_COLOR = 'var(--color-hairline)'

/** 结论类取值的语义着色：未/不 开头警示，已/完成/合格 正常。 */
function bucketColor(key: string): string {
  if (key.startsWith('未') || key.startsWith('不')) return WARNING_COLOR
  if (key.startsWith('已') || key.includes('完成') || key.includes('合格')) {
    return SUCCESS_COLOR
  }
  return NEUTRAL_COLOR
}

function monthLabel(key: string): string {
  const match = /^(\d{4})-(\d{2})$/.exec(key)
  if (!match) return key
  return `${Number(match[2])}月`
}

function buildMonthOption(buckets: { key: string; count: number }[]): EChartsOption {
  const showYear = new Set(buckets.map((bucket) => bucket.key.slice(0, 4))).size > 1
  return {
    grid: { left: 8, right: 12, top: 26, bottom: 4, containLabel: true },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: buckets.map((bucket) => showYear ? `${bucket.key.slice(0, 4)}年${monthLabel(bucket.key)}` : monthLabel(bucket.key)),
      axisTick: { show: false },
      axisLine: { lineStyle: { color: AXIS_LINE_COLOR } },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: SPLIT_LINE_COLOR } },
    },
    series: [
      {
        type: 'bar',
        name: '隐患数',
        data: buckets.map((bucket) => bucket.count),
        barMaxWidth: 26,
        itemStyle: { color: PRIMARY_COLOR, borderRadius: [4, 4, 0, 0] },
        label: { show: true, position: 'top', fontSize: 11 },
      },
    ],
  }
}

function buildWorkshopOption(buckets: { key: string; count: number }[]): EChartsOption {
  const ordered = [...buckets].reverse() // 条形图自下而上，反转后最大值在最上
  return {
    grid: { left: 8, right: 34, top: 8, bottom: 4, containLabel: true },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: SPLIT_LINE_COLOR } },
    },
    yAxis: {
      type: 'category',
      data: ordered.map((bucket) => bucket.key),
      axisTick: { show: false },
      axisLine: { lineStyle: { color: AXIS_LINE_COLOR } },
      axisLabel: { fontSize: 11 },
    },
    series: [
      {
        type: 'bar',
        name: '隐患数',
        data: ordered.map((bucket) => bucket.count),
        barMaxWidth: 13,
        itemStyle: { color: WORKSHOP_COLOR, borderRadius: [0, 4, 4, 0] },
        label: { show: true, position: 'right', fontSize: 11 },
      },
    ],
  }
}

function buildStatusOption(
  buckets: { key: string; count: number }[],
  total: number
): EChartsOption {
  return {
    tooltip: { trigger: 'item', formatter: '{b}：{c}（{d}%）' },
    title: {
      text: String(total),
      subtext: '隐患总数',
      left: 'center',
      top: '30%',
      textStyle: { fontSize: 24, fontWeight: 600, color: 'var(--color-ink)' },
      subtextStyle: { fontSize: 12, color: 'var(--color-slate)' },
    },
    legend: {
      bottom: 0,
      icon: 'circle',
      itemWidth: 8,
      itemHeight: 8,
      textStyle: { fontSize: 11 },
    },
    series: [
      {
        type: 'pie',
        name: '整改情况',
        radius: ['58%', '82%'],
        center: ['50%', '42%'],
        avoidLabelOverlap: false,
        label: { show: false },
        labelLine: { show: false },
        data: buckets.map((bucket) => ({
          name: bucket.key,
          value: bucket.count,
          itemStyle: { color: bucketColor(bucket.key) },
        })),
      },
    ],
  }
}

function ChartCard({
  title,
  option,
  hasData,
  onSelect,
  fieldName,
  selectionKeys,
}: {
  title: string
  option: EChartsOption
  hasData: boolean
  onSelect?: (field: string, key: string) => void
  fieldName?: string
  selectionKeys?: string[]
}) {
  return (
    <Card
      size="small"
      title={title}
      style={{ flex: 1, minWidth: 320 }}
      styles={{ body: { paddingBlock: 10 } }}
    >
      {hasData ? (
        <>
          <ReactECharts
            option={option}
            style={{ height: CHART_HEIGHT }}
            notMerge
            onEvents={
              onSelect && fieldName
                ? {
                    click: (params: { name?: string; dataIndex?: number }) => {
                      const key = params.dataIndex === undefined ? params.name : selectionKeys?.[params.dataIndex] ?? params.name
                      if (key) onSelect(fieldName, key)
                    },
                  }
                : undefined
            }
          />
          {onSelect && fieldName ? (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              点击图中分类可筛选下方明细
            </Typography.Text>
          ) : null}
        </>
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ height: CHART_HEIGHT, margin: 0 }} />
      )}
    </Card>
  )
}

/** 分组卡片标题：月度趋势固定；单选环形用字段名（关闭状态沿用「整改情况」）；
 * 人员/文本等分布类加「分布」后缀。 */
function groupTitle(group: PageTableStats['groups'][number]): string {
  if (group.mode === 'month') return '月度隐患趋势'
  if (group.kind === 'select' || group.kind === 'multi_select') {
    return group.field === '关闭状态' ? '整改情况' : group.field
  }
  return `${group.field}分布`
}

/** 页面顶部仪表盘：按统计分组渲染一行图表卡（月份柱状 / 单选环形 /
 * 人员、文本等横向条形），点击图中分类可下钻筛选下方明细列表。 */
export default function PageFeishuStatsBar({
  stats,
  onSelect,
}: {
  stats: PageTableStats | null
  onSelect?: (field: string, key: string) => void
}) {
  if (!stats || stats.groups.length === 0) return null

  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'stretch', overflowX: 'auto' }}>
      {stats.groups.map((group) => {
        const isDonut = group.kind === 'select' || group.kind === 'multi_select'
        return (
          <ChartCard
            key={group.field}
            title={groupTitle(group)}
            option={
              group.mode === 'month'
                ? buildMonthOption(group.buckets)
                : isDonut
                  ? buildStatusOption(group.buckets, stats.total)
                  : buildWorkshopOption(group.buckets)
            }
            hasData={Boolean(group.buckets.length)}
            onSelect={onSelect}
            fieldName={group.field}
            selectionKeys={group.buckets.map((bucket) => bucket.key)}
          />
        )
      })}
    </div>
  )
}
