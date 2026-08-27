'use client'

import dayjs from 'dayjs'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Button, Drawer, Empty, Spin, Switch, Table, Tag } from 'antd'
import type { TableColumnsType } from 'antd'
import {
  ReloadOutlined,
  DatabaseOutlined,
  DollarOutlined,
  CheckCircleOutlined,
  WarningOutlined,
  InboxOutlined,
  RiseOutlined,
} from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import { graphic } from 'echarts'
import type { EChartsOption } from 'echarts'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchWarehouseDashboard as fetchDashboardClient } from '@/lib/api/client/warehouse'
import type {
  WarehouseDashboardData,
  WarehouseDashboardDeptValue,
  WarehouseDashboardGroup,
  WarehouseDashboardNameValue,
  WarehouseDashboardTrendPoint,
  WarehouseProductMonthlyData,
} from '@/types/warehouse'

interface WarehouseDashboardProps {
  group: WarehouseDashboardGroup
  title: string
  baseName: string
  initialData: WarehouseDashboardData | null
}

// 企业年报级高级配色板
const PALETTE = ['#5645d4', '#1677ff', '#52c41a', '#fa8c16', '#ff4d4f', '#722ed1', '#13c2c2', '#eb2f96']
const BRAND = '#5645d4'

function formatNumber(value: number, decimals = 0): string {
  return value.toLocaleString('zh-CN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

// 数字滚动动画（easeOut）
function useCountUp(target: number, duration = 900): number {
  const [value, setValue] = useState(0)
  const fromRef = useRef(0)
  useEffect(() => {
    const from = fromRef.current
    let raf = 0
    const start = performance.now()
    const tick = (now: number) => {
      const progress = Math.min((now - start) / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      const next = from + (target - from) * eased
      setValue(next)
      if (progress < 1) {
        raf = requestAnimationFrame(tick)
      } else {
        fromRef.current = target
      }
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, duration])
  return value
}

// 高级 tooltip（白底圆角阴影）
function baseTooltip(trigger: 'axis' | 'item' = 'axis') {
  return {
    trigger,
    backgroundColor: '#ffffff',
    borderColor: '#ececf4',
    borderWidth: 1,
    textStyle: { color: '#333', fontSize: 12 },
    extraCssText: 'box-shadow:0 6px 20px rgba(26,42,82,0.14);border-radius:10px;',
  } as const
}

function areaGradient(hex: string): graphic.LinearGradient {
  return new graphic.LinearGradient(0, 0, 0, 1, [
    { offset: 0, color: `${hex}40` },
    { offset: 1, color: `${hex}00` },
  ])
}

function barGradient(hex: string): graphic.LinearGradient {
  return new graphic.LinearGradient(0, 0, 0, 1, [
    { offset: 0, color: hex },
    { offset: 1, color: `${hex}99` },
  ])
}

function lineOption(points: WarehouseDashboardTrendPoint[], color = BRAND): EChartsOption {
  return {
    color: PALETTE,
    tooltip: baseTooltip(),
    grid: { left: 48, right: 24, top: 32, bottom: 56 },
    xAxis: {
      type: 'category',
      data: points.map((item) => item.date.slice(5)),
      axisLabel: { fontSize: 10, rotate: 45, color: '#8a8fa3' },
      axisLine: { lineStyle: { color: '#e3e5ef' } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#8a8fa3' },
      splitLine: { lineStyle: { type: 'dashed', color: '#eef0f7' } },
    },
    series: [
      {
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        data: points.map((item) => item.value),
        lineStyle: { width: 3, color },
        itemStyle: { color, borderColor: '#fff', borderWidth: 1.5 },
        areaStyle: { color: areaGradient(color) },
      },
    ],
  }
}

function barOption(
  items: Array<WarehouseDashboardNameValue | WarehouseDashboardDeptValue>,
  color = BRAND
): EChartsOption {
  return {
    color: PALETTE,
    tooltip: { ...baseTooltip(), axisPointer: { type: 'shadow' } },
    grid: { left: 96, right: 24, top: 16, bottom: 32 },
    xAxis: {
      type: 'value',
      axisLabel: { color: '#8a8fa3' },
      splitLine: { lineStyle: { type: 'dashed', color: '#eef0f7' } },
    },
    yAxis: {
      type: 'category',
      data: items.map((item) => ('name' in item ? item.name : item.dept)),
      axisLabel: { fontSize: 11, color: '#5a5f73' },
      axisLine: { lineStyle: { color: '#e3e5ef' } },
      axisTick: { show: false },
    },
    series: [
      {
        type: 'bar',
        data: items.map((item) => item.value),
        itemStyle: { color: barGradient(color), borderRadius: [0, 6, 6, 0] },
        barMaxWidth: 14,
      },
    ],
  }
}

// 每产品单系列柱状图（全年趋势，入库/出库各一张独立图）
function productBarOption(months: string[], values: number[], color = BRAND): EChartsOption {
  return {
    color: PALETTE,
    tooltip: { ...baseTooltip(), axisPointer: { type: 'shadow' } },
    grid: { left: 56, right: 24, top: 32, bottom: 48 },
    xAxis: {
      type: 'category',
      data: months,
      axisLabel: { fontSize: 10, rotate: 45, color: '#8a8fa3' },
      axisLine: { lineStyle: { color: '#e3e5ef' } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#8a8fa3' },
      splitLine: { lineStyle: { type: 'dashed', color: '#eef0f7' } },
    },
    series: [
      {
        name: '数量',
        type: 'bar',
        data: values,
        itemStyle: { color: barGradient(color), borderRadius: [6, 6, 0, 0] },
        barMaxWidth: 18,
      },
    ],
  }
}

interface KpiCardProps {
  icon: React.ReactNode
  label: string
  value: number
  prefix?: string
  suffix?: string
  color: string
  decimals?: number
  hint?: string
  onClick?: () => void
}

interface DetailColumn {
  title: string
  dataIndex: string
}

// 支持点击查看明细的 KPI 卡片元信息
interface KpiMeta extends KpiCardProps {
  detailKey?: string
  detailLink?: string
  detailColumns?: DetailColumn[]
}

function KpiCard({ icon, label, value, prefix, suffix, color, decimals = 0, hint, onClick }: KpiCardProps) {
  const animated = useCountUp(value)
  return (
    <div
      className={`wh-kpi group relative overflow-hidden rounded-xl border border-[var(--color-hairline)] bg-white p-4 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg${onClick ? ' cursor-pointer' : ''}`}
      onClick={onClick}
    >
      <div
        className="pointer-events-none absolute inset-y-0 left-0 w-1"
        style={{ background: `linear-gradient(180deg, ${color}, ${color}66)` }}
      />
      <div className="flex items-start gap-3">
        <div
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-[20px] text-white"
          style={{ background: `linear-gradient(135deg, ${color}, ${color}bb)` }}
        >
          {icon}
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[12px] font-medium text-[var(--color-steel)]">{label}</div>
          <div className="mt-1 text-[24px] font-bold leading-none tracking-tight" style={{ color }}>
            {prefix}
            {formatNumber(animated, decimals)}
            {suffix && <span className="ml-1 text-[13px] font-medium text-[var(--color-steel)]">{suffix}</span>}
          </div>
          {onClick ? (
            <div className="mt-1.5 truncate text-[11px] text-[var(--color-primary)]">点击查看明细</div>
          ) : hint ? (
            <div className="mt-1.5 truncate text-[11px] text-[var(--color-muted)]">{hint}</div>
          ) : null}
        </div>
      </div>
    </div>
  )
}

function ChartCard({ title, subtitle, option, height = 300 }: { title: string; subtitle?: string; option: EChartsOption; height?: number }) {
  return (
    <div className="wh-chart overflow-hidden rounded-xl border border-[var(--color-hairline)] bg-white shadow-sm transition-all duration-200 hover:shadow-md">
      <div className="flex items-center gap-2 border-b border-[var(--color-hairline)] px-4 py-3">
        <span className="h-4 w-1 rounded-full" style={{ background: BRAND }} />
        <span className="text-[14px] font-semibold text-[var(--color-charcoal)]">{title}</span>
        {subtitle ? <span className="ml-auto text-[11px] text-[var(--color-muted)]">{subtitle}</span> : null}
      </div>
      <div className="p-3">
        <ReactECharts option={option} style={{ height }} notMerge lazyUpdate />
      </div>
    </div>
  )
}

export function WarehouseDashboard({ group, title, baseName, initialData }: WarehouseDashboardProps) {
  const queryClient = useQueryClient()
  const [autoRefresh, setAutoRefresh] = useState(false)
  const [syncedAt, setSyncedAt] = useState<string>('')

  const queryKey = ['warehouse-dashboard', group] as const
  const { data, isFetching } = useQuery({
    queryKey,
    queryFn: () => fetchDashboardClient(group, false, true),
    initialData: initialData ?? undefined,
    refetchInterval: autoRefresh ? 60000 : false,
  })

  const refreshMutation = useMutation({
    mutationFn: (force: boolean) => fetchDashboardClient(group, force, true),
    onSuccess: (latest) => {
      queryClient.setQueryData(queryKey, latest)
    },
  })

  const loading = isFetching || refreshMutation.isPending

  useEffect(() => {
    setSyncedAt(dayjs().format('YYYY-MM-DD HH:mm:ss'))
  }, [data])

  const raw = group === 'raw' ? (data as WarehouseRawDashboardLike | null) : null
  const hardware = group === 'hardware' ? (data as WarehouseHardwareDashboardLike | null) : null
  const product = group === 'product' ? (data as WarehouseProductDashboardLike | null | undefined) : null

  // ── 卡片点击查看明细（抽屉）──────────────────────────────
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailTitle, setDetailTitle] = useState('')
  const [detailRows, setDetailRows] = useState<Array<Record<string, unknown>>>([])
  const [detailColumns, setDetailColumns] = useState<DetailColumn[]>([])
  const [detailLink, setDetailLink] = useState('')

  const openKpiDetail = (kpi: KpiMeta) => {
    if (!kpi.detailKey || !data) {
      return
    }
    const detail = (data as { detail?: Record<string, unknown> }).detail
    const rows = ((detail?.[kpi.detailKey] as Array<Record<string, unknown>> | undefined) ?? []).map(
      (row, index) => ({ ...row, __row_index: index })
    )
    setDetailTitle(kpi.label)
    setDetailRows(rows)
    setDetailColumns(kpi.detailColumns ?? [])
    setDetailLink(kpi.detailLink ?? '')
    setDetailOpen(true)
  }

  const detailTableColumns: TableColumnsType<Record<string, unknown>> = useMemo(
    () =>
      detailColumns.map((column) => ({
        title: column.title,
        dataIndex: column.dataIndex,
        key: column.dataIndex,
        align: 'center' as const,
        onCell: () => ({
          style: { whiteSpace: 'normal' as const, wordBreak: 'break-word' as const },
        }),
      })),
    [detailColumns]
  )

  const kpis = useMemo(() => {
    const list: KpiMeta[] = []
    if (raw) {
      list.push({
        icon: <CheckCircleOutlined />,
        label: '安全库存达标',
        value: raw.safety.ok,
        color: '#52c41a',
        hint: `共 ${raw.safety.total} 项`,
        detailKey: 'safety_ok',
        detailLink: '/warehouse/materials/raw-summary',
        detailColumns: [
          { title: '物料名称', dataIndex: 'name' },
          { title: '本日结存', dataIndex: 'balance' },
          { title: '可用库存', dataIndex: 'effective_balance' },
          { title: '安全库存', dataIndex: 'safety' },
        ],
      })
      list.push({
        icon: <WarningOutlined />,
        label: '库存不足',
        value: raw.safety.low,
        color: '#fa8c16',
        hint: '需补货',
        detailKey: 'safety_low',
        detailLink: '/warehouse/materials/raw-summary',
        detailColumns: [
          { title: '物料名称', dataIndex: 'name' },
          { title: '本日结存', dataIndex: 'balance' },
          { title: '可用库存', dataIndex: 'effective_balance' },
          { title: '安全库存', dataIndex: 'safety' },
          { title: '预警', dataIndex: 'warning' },
        ],
      })
      list.push({
        icon: <InboxOutlined />,
        label: '待验',
        value: raw.quality['待验'],
        color: '#faad14',
        detailKey: 'pending',
        detailLink: '/warehouse/materials/raw-detail?quality_status=待验',
        detailColumns: [
          { title: '物料名称', dataIndex: 'name' },
          { title: '厂内批号', dataIndex: 'batch' },
          { title: '本日结存', dataIndex: 'balance' },
          { title: '质量状态', dataIndex: 'quality_status' },
          { title: '库区', dataIndex: 'area' },
        ],
      })
      list.push({
        icon: <RiseOutlined />,
        label: '本月入库',
        value: raw.month_inbound_total,
        color: '#1677ff',
        detailKey: 'month_inbound',
        detailLink: '/warehouse/materials/inbound-ledger',
        detailColumns: [
          { title: '入库日期', dataIndex: 'date' },
          { title: '物料类别', dataIndex: 'category' },
          { title: '物料名称', dataIndex: 'name' },
          { title: '规格', dataIndex: 'spec' },
          { title: '厂内批号', dataIndex: 'batch' },
          { title: '入库数量', dataIndex: 'quantity' },
          { title: '供应商', dataIndex: 'supplier' },
        ],
      })
    }
    if (hardware) {
      list.push({
        icon: <DollarOutlined />,
        label: '五金库存金额',
        value: hardware.stock_amount,
        prefix: '¥',
        color: BRAND,
        decimals: 2,
        detailKey: 'dept_stock',
        detailLink: '/warehouse/hardware/dashboard',
        detailColumns: [
          { title: '部门', dataIndex: 'dept' },
          { title: '金额', dataIndex: 'value' },
        ],
      })
      list.push({
        icon: <RiseOutlined />,
        label: '30天入库金额',
        value: hardware.inbound_30d_total,
        prefix: '¥',
        color: '#52c41a',
        decimals: 2,
        detailKey: 'inbound_30d',
        detailLink: '/warehouse/hardware/dashboard',
        detailColumns: [
          { title: '日期', dataIndex: 'date' },
          { title: '物料名称', dataIndex: 'name' },
          { title: '规格', dataIndex: 'spec' },
          { title: '入库量', dataIndex: 'quantity' },
          { title: '单价', dataIndex: 'price' },
          { title: '金额', dataIndex: 'amount' },
        ],
      })
      list.push({
        icon: <DatabaseOutlined />,
        label: '30天出库金额',
        value: hardware.outbound_30d_total,
        prefix: '¥',
        color: '#fa8c16',
        decimals: 2,
        detailKey: 'outbound_30d',
        detailLink: '/warehouse/hardware/dashboard',
        detailColumns: [
          { title: '日期', dataIndex: 'date' },
          { title: '物料名称', dataIndex: 'name' },
          { title: '规格', dataIndex: 'spec' },
          { title: '部门', dataIndex: 'dept' },
          { title: '金额', dataIndex: 'amount' },
        ],
      })
    }
    if (product) {
      list.push({
        icon: <CheckCircleOutlined />,
        label: '合格数量',
        value: product.qualified,
        color: '#52c41a',
        detailKey: 'qualified',
        detailLink: '/warehouse/product/summary',
        detailColumns: [
          { title: '产品名称', dataIndex: 'name' },
          { title: '合格数量', dataIndex: 'value' },
        ],
      })
      list.push({
        icon: <InboxOutlined />,
        label: '待检数量',
        value: product.pending,
        color: '#faad14',
        detailKey: 'pending',
        detailLink: '/warehouse/product/summary',
        detailColumns: [
          { title: '产品名称', dataIndex: 'name' },
          { title: '待检数量', dataIndex: 'value' },
        ],
      })
    }
    return list
  }, [raw, hardware, product])

  const charts = useMemo(() => {
    const list: Array<{ key: string; title: string; subtitle?: string; option: EChartsOption; full?: boolean }> = []
    if (raw) {
      list.push({ key: 'trend', title: '30 天物料出库量趋势', option: lineOption(raw.material_outbound_30d) })
      list.push({
        key: 'low-stock',
        title: '库存不足 / 严重不足物料 Top',
        option: barOption(raw.low_stock_top.map((item) => ({ name: `${item.name}（${item.warning}）`, value: item.balance })), '#fa8c16'),
      })
    }
    if (hardware) {
      list.push({ key: 'dept-stock', title: '各部门库存五金金额', option: barOption(hardware.dept_stock) })
      list.push({ key: 'out-trend', title: '30 天五金出库金额趋势', option: lineOption(hardware.outbound_30d_trend, '#fa8c16') })
      list.push({ key: 'dept-out', title: '各部门 30 天出库金额', option: barOption(hardware.dept_outbound_30d, '#1677ff'), full: true })
    }
    if (product) {
      list.push({ key: 'pending', title: '各产品待验数量', option: barOption(product.product_pending, '#faad14') })
      list.push({ key: 'qualified', title: '各产品合格数量', option: barOption(product.product_qualified, '#52c41a') })
      list.push({ key: 'ship-trend', title: '30 天发货趋势', option: lineOption(product.shipping_30d_trend), full: true })
    }
    return list
  }, [raw, hardware, product])

  // 常见规格后缀：将「盐酸林可霉素（kg）/（十亿）」归并为同一产品行
  function stripSpecSuffix(name: string): string {
    const SPEC_SUFFIXES = ['kg', 'g', 'mg', '十亿', '亿', '万', 't', '瓶', '箱', '桶']
    const trimmed = name.trim()
    // 括号内规格后缀（如「盐酸林可霉素（kg）」「盐酸林可霉素（十亿）」）：
    // 仅当括号内容命中规格后缀才移除，避免误删「霉酚酸（高规）」这类业务后缀
    const bracketed = trimmed.match(/^(.+?)[（(]\s*([^）)]+)\s*[）)]$/)
    if (bracketed) {
      const suffix = bracketed[2].trim().toLowerCase()
      if (SPEC_SUFFIXES.includes(suffix)) {
        return bracketed[1].trim() || trimmed
      }
    }
    let base = trimmed
    for (const s of SPEC_SUFFIXES) {
      if (base.toLowerCase().endsWith(s)) {
        base = base.slice(0, -s.length).trim()
        break
      }
    }
    return base || trimmed
  }

  // 各产品全年出入库对比：一个产品一行，行内入库/出库并排，同产品不同规格数据合并
  const productMonthlyGroups = useMemo(() => {
    const inbound = product?.product_monthly_inbound ?? {}
    const outbound = product?.product_monthly_outbound ?? {}
    const allNames = new Set([...Object.keys(inbound), ...Object.keys(outbound)])
    const groups = new Map<
      string,
      {
        name: string
        inboundMonths: string[]
        inboundValues: number[]
        inboundTotal: number
        outboundMonths: string[]
        outboundValues: number[]
        outboundTotal: number
      }
    >()
    allNames.forEach((name) => {
      const inVals = inbound[name] ?? []
      const outVals = outbound[name] ?? []
      const base = stripSpecSuffix(name)
      const entry = groups.get(base) ?? {
        name: base,
        inboundMonths: [],
        inboundValues: [],
        inboundTotal: 0,
        outboundMonths: [],
        outboundValues: [],
        outboundTotal: 0,
      }
      // 合并同产品不同规格的数据（如林可霉素 kg + 十亿）
      const inMonths = inVals.map((v) => v.month)
      const outMonths = outVals.map((v) => v.month)
      const allMonths = Array.from(new Set([...inMonths, ...outMonths])).sort()
      allMonths.forEach((m) => {
        const inQty = inVals.find((v) => v.month === m)?.quantity ?? 0
        const outQty = outVals.find((v) => v.month === m)?.quantity ?? 0
        // 入库
        const inIdx = entry.inboundMonths.indexOf(m)
        if (inIdx >= 0) {
          entry.inboundValues[inIdx] += inQty
        } else if (inQty > 0) {
          entry.inboundMonths.push(m)
          entry.inboundValues.push(inQty)
        }
        // 出库
        const outIdx = entry.outboundMonths.indexOf(m)
        if (outIdx >= 0) {
          entry.outboundValues[outIdx] += outQty
        } else if (outQty > 0) {
          entry.outboundMonths.push(m)
          entry.outboundValues.push(outQty)
        }
        entry.inboundTotal += inQty
        entry.outboundTotal += outQty
      })
      groups.set(base, entry)
    })
    const cmp = (a: string, b: string) => a.localeCompare(b, 'zh-Hans-CN')
    return Array.from(groups.values())
      .sort((a, b) => cmp(a.name, b.name))
      .map((g) => ({
        ...g,
        inboundOption: productBarOption(g.inboundMonths, g.inboundValues, '#52c41a'),
        outboundOption: productBarOption(g.outboundMonths, g.outboundValues, '#fa8c16'),
      }))
  }, [product])

  return (
    <div className="w-full">
      {/* 品牌渐变头图 */}
      <div
        className="relative mb-5 overflow-hidden rounded-2xl px-6 py-6 text-white shadow-md"
        style={{ background: 'linear-gradient(135deg, #1a2a52 0%, #3b4db8 55%, #5645d4 100%)' }}
      >
        <div className="pointer-events-none absolute -right-16 -top-20 h-56 w-56 rounded-full bg-white/10" />
        <div className="pointer-events-none absolute -bottom-24 right-24 h-44 w-44 rounded-full bg-white/5" />
        <div className="relative flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-[12px] font-medium uppercase tracking-[0.2em] text-white/70">WAREHOUSE ANALYTICS</div>
            <h1 className="mt-1 text-[26px] font-bold leading-tight">{title}</h1>
            <div className="mt-1 text-[13px] text-white/80">{baseName}多维表格 · 实时经营数据概览</div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <span className="rounded-full bg-white/15 px-3 py-1 text-[12px] backdrop-blur">
              {syncedAt ? `同步于 ${syncedAt}` : '同步中'}
            </span>
            <span className="flex items-center gap-1.5 text-[12px] text-white/85">
              自动刷新
              <Switch size="small" checked={autoRefresh} onChange={setAutoRefresh} />
            </span>
            <Button
              type="primary"
              ghost
              icon={<ReloadOutlined />}
              onClick={() => refreshMutation.mutate(true)}
              loading={loading}
            >
              刷新
            </Button>
          </div>
        </div>
      </div>

      <Spin spinning={loading}>
        {!data ? (
          <div className="rounded-xl border border-[var(--color-hairline)] bg-white p-10 shadow-sm">
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="数据暂时不可用，请稍后重试" />
          </div>
        ) : (
          <>
            <div className="mb-5 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
              {kpis.map((kpi) => (
                <KpiCard
                  key={kpi.label}
                  {...kpi}
                  onClick={
                    kpi.detailKey
                      ? () => {
                          openKpiDetail(kpi)
                        }
                      : undefined
                  }
                />
              ))}
            </div>

            <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
              {charts.map((chart) => (
                <div key={chart.key} className={chart.full ? 'xl:col-span-2' : ''}>
                  <ChartCard title={chart.title} subtitle={chart.subtitle} option={chart.option} />
                </div>
              ))}
            </div>

            {productMonthlyGroups.length > 0 && (
              <div className="mt-4 space-y-4">
                {productMonthlyGroups.map((group) => (
                  <div
                    key={group.name}
                    className="overflow-hidden rounded-xl border border-[var(--color-hairline)] bg-white shadow-sm"
                  >
                    <div className="flex items-center gap-2 border-b border-[var(--color-hairline)] px-4 py-3">
                      <span
                        className="h-4 w-1 rounded-full"
                        style={{ background: 'linear-gradient(#52c41a 0%, #fa8c16 100%)' }}
                      />
                      <span className="text-[14px] font-semibold text-[var(--color-charcoal)]">
                        {group.name} 全年出入库量
                      </span>
                      <span className="ml-auto text-[11px] text-[var(--color-muted)]">
                        入库 {group.inboundTotal} · 出库 {group.outboundTotal}
                      </span>
                    </div>
                    <div className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2">
                      <div>
                        <div className="mb-2 flex items-center gap-2">
                          <span className="h-3 w-1 rounded-full" style={{ background: '#52c41a' }} />
                          <span className="text-[13px] font-medium text-[var(--color-charcoal)]">入库</span>
                        </div>
                        <ReactECharts option={group.inboundOption} style={{ height: 280 }} notMerge lazyUpdate />
                      </div>
                      <div>
                        <div className="mb-2 flex items-center gap-2">
                          <span className="h-3 w-1 rounded-full" style={{ background: '#fa8c16' }} />
                          <span className="text-[13px] font-medium text-[var(--color-charcoal)]">出库</span>
                        </div>
                        <ReactECharts option={group.outboundOption} style={{ height: 280 }} notMerge lazyUpdate />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {product?.zero_activity_products && product.zero_activity_products.length > 0 && (
              <div className="mt-4 overflow-hidden rounded-xl border border-[var(--color-hairline)] bg-white shadow-sm">
                <div className="flex items-center gap-2 border-b border-[var(--color-hairline)] px-4 py-3">
                  <span className="h-4 w-1 rounded-full" style={{ background: '#ff4d4f' }} />
                  <span className="text-[14px] font-semibold text-[var(--color-charcoal)]">
                    2026 年零活动产品（入库 + 出库均为 0）
                  </span>
                </div>
                <div className="flex flex-wrap gap-2 p-4">
                  {product.zero_activity_products.map((p) => (
                    <Tag key={p} color="red">{p}</Tag>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </Spin>

      {/* KPI 卡片点击明细抽屉 */}
      <Drawer
        title={`${detailTitle}明细（共 ${detailRows.length} 条）`}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        size={960}
        extra={
          detailLink ? (
            <Button
              type="link"
              href={detailLink}
              target="_blank"
              rel="noreferrer"
              icon={<DatabaseOutlined />}
            >
              前往原表查看
            </Button>
          ) : null
        }
      >
        <Table<Record<string, unknown>>
          columns={detailTableColumns}
          dataSource={detailRows}
          rowKey="__row_index"
          size="small"
          locale={{
            emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无明细数据" />,
          }}
          pagination={{
            pageSize: 20,
            showSizeChanger: true,
            pageSizeOptions: [20, 50, 100],
            showTotal: (total) => `共 ${total} 条`,
          }}
          scroll={{ x: 'max-content', y: 480 }}
        />
      </Drawer>
    </div>
  )
}

// 展示用最小结构（数据来自后端，避免与类型强耦合）
interface WarehouseRawDashboardLike {
  safety: { total: number; ok: number; low: number }
  quality: { '合格': number; '待验': number; '不合格': number }
  material_outbound_30d: WarehouseDashboardTrendPoint[]
  packaging_outbound_30d_total: number
  month_inbound_total: number
  low_stock_top: Array<{ name: string; balance: number; safety: number; warning: string }>
}

interface WarehouseHardwareDashboardLike {
  stock_amount: number
  dept_stock: WarehouseDashboardDeptValue[]
  inbound_30d_total: number
  outbound_30d_total: number
  outbound_30d_trend: WarehouseDashboardTrendPoint[]
  dept_outbound_30d: WarehouseDashboardDeptValue[]
}

interface WarehouseProductDashboardLike {
  qualified: number
  pending: number
  product_stock: WarehouseDashboardNameValue[]
  product_outbound: WarehouseDashboardNameValue[]
  product_qualified: WarehouseDashboardNameValue[]
  product_pending: WarehouseDashboardNameValue[]
  shipping_30d_trend: WarehouseDashboardTrendPoint[]
  product_monthly_inbound?: WarehouseProductMonthlyData
  product_monthly_outbound?: WarehouseProductMonthlyData
  zero_activity_products?: string[]
}

export default WarehouseDashboard
