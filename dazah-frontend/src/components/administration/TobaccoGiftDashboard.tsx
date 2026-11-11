'use client'

import { ReloadOutlined, SettingOutlined } from '@ant-design/icons'
import { Button, Card, Empty, Space, Tooltip, Typography, theme } from 'antd'
import type { EChartsOption } from 'echarts'
import { useRouter } from 'next/navigation'
import { useTransition } from 'react'

import PlatformNotice from '@/components/shared/PlatformNotice'
import ThemedEChart from '@/components/shared/ThemedEChart'
import type { TobaccoGiftChartItem, TobaccoGiftDashboardStats } from '@/types/administration'

interface TobaccoGiftDashboardProps {
  stats: TobaccoGiftDashboardStats | null
  error?: string | null
}

const AXIS_LABEL_COLOR = 'var(--color-slate)'
const SPLIT_LINE_COLOR = 'var(--color-hairline-soft)'

export function formatQuantity(value: number): string {
  return Number.isInteger(value) ? value.toLocaleString('zh-CN') : value.toFixed(1)
}

export function formatMoney(value: number): string {
  return `¥${value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`
}

/** 固定东八区：同步时间在 SSR 渲染，服务端（UTC 容器）与浏览器必须输出一致，避免水合不匹配。 */
export function formatSyncedAt(value: string | null | undefined): string {
  if (!value) return '尚未同步'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? '尚未同步'
    : date.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })
}

const collator = new Intl.Collator('zh-Hans-CN')

/** 按物品名称排序（与行政侧飞书仪表盘的横轴顺序一致）。 */
export function sortByName(data: TobaccoGiftChartItem[]): TobaccoGiftChartItem[] {
  return [...data].sort((left, right) => collator.compare(left.name, right.name))
}

/** 竖向柱状图：横轴物品/人员名称（旋转防重叠），柱多的图不显示柱顶数值。 */
export function buildBarOption(
  data: TobaccoGiftChartItem[],
  seriesName: string,
  color: string,
  money = false,
): EChartsOption {
  const format = (value: number) => (money ? formatMoney(value) : formatQuantity(value))
  const sorted = sortByName(data)
  const showLabels = sorted.length <= 15
  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      valueFormatter: (value) => format(Number(value ?? 0)),
    },
    grid: { left: 12, right: 12, top: showLabels ? 28 : 12, bottom: 8, containLabel: true },
    xAxis: {
      type: 'category',
      data: sorted.map((item) => item.name),
      axisLabel: {
        rotate: 45,
        interval: 0,
        width: 72,
        overflow: 'truncate',
        fontSize: 11,
        color: AXIS_LABEL_COLOR,
      },
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        color: AXIS_LABEL_COLOR,
        formatter: (value: number) => (money ? formatMoney(value) : String(value)),
      },
      splitLine: { lineStyle: { type: 'dashed', color: SPLIT_LINE_COLOR } },
    },
    series: [
      {
        name: seriesName,
        type: 'bar',
        data: sorted.map((item) => item.value),
        barMaxWidth: 22,
        itemStyle: { color, borderRadius: [4, 4, 0, 0] },
        label: {
          show: showLabels,
          position: 'top',
          fontSize: 11,
          color: AXIS_LABEL_COLOR,
          formatter: (params) => format(Number(params.value ?? 0)),
        },
      },
    ],
  }
}

interface ChartCardProps {
  title: string
  seriesName: string
  data: TobaccoGiftChartItem[]
  color: string
  money?: boolean
  height?: number
  note?: string
}

function ChartCard({ title, seriesName, data, color, money, height = 320, note }: ChartCardProps) {
  return (
    <Card
      size="small"
      title={title}
      extra={note ? <Typography.Text type="secondary" style={{ fontSize: 12 }}>{note}</Typography.Text> : null}
      styles={{ body: { paddingTop: 8 } }}
    >
      {data.length ? (
        <ThemedEChart
          option={buildBarOption(data, seriesName, color, money)}
          style={{ height }}
          notMerge
          lazyUpdate
        />
      ) : (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="暂无统计数据"
          style={{ padding: '48px 0' }}
        />
      )}
    </Card>
  )
}

interface MetricCardProps {
  label: string
  value: string
  accent: string
  hint?: string
}

function MetricCard({ label, value, accent, hint }: MetricCardProps) {
  const { token } = theme.useToken()
  return (
    <div
      style={{
        background: token.colorBgContainer,
        border: `1px solid ${token.colorBorderSecondary}`,
        borderRadius: token.borderRadiusLG,
        padding: '18px 20px',
        minHeight: 112,
      }}
    >
      <Typography.Text style={{ color: accent, fontSize: 14 }}>{label}</Typography.Text>
      <div
        style={{
          marginTop: 8,
          fontSize: 40,
          lineHeight: 1.1,
          fontWeight: 700,
          color: accent,
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        {value}
      </div>
      {hint ? (
        <Typography.Text type="secondary" style={{ display: 'block', marginTop: 6, fontSize: 12 }}>
          {hint}
        </Typography.Text>
      ) : null}
    </div>
  )
}

export function TobaccoGiftDashboard({ stats, error }: TobaccoGiftDashboardProps) {
  const { token } = theme.useToken()
  const router = useRouter()
  const [refreshing, startRefresh] = useTransition()

  const missingTables = stats
    ? [
        stats.inventory_synced_at ? null : '物品清单',
        stats.requisition_synced_at ? null : '领用记录',
      ].filter((name): name is string => name !== null)
    : []
  const notSetUp = missingTables.length === 2
  const partiallySetUp = missingTables.length === 1

  return (
    <main className="mx-auto max-w-[1600px] px-6 py-7">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div>
          <Typography.Title level={3} className="!mb-1">
            烟酒礼品仪表台
          </Typography.Title>
          <Typography.Text type="secondary">
            数据来自飞书多维表格本地镜像 · 物品清单同步于
            {formatSyncedAt(stats?.inventory_synced_at)} · 领用记录同步于
            {formatSyncedAt(stats?.requisition_synced_at)}
          </Typography.Text>
        </div>
        <Space wrap>
          <Tooltip title="重新读取本地镜像数据（不含飞书重新同步；手动同步在飞书设置页）">
            <Button
              icon={<ReloadOutlined />}
              loading={refreshing}
              onClick={() => startRefresh(() => router.refresh())}
            >
              刷新
            </Button>
          </Tooltip>
        </Space>
      </div>

      {error ? (
        <PlatformNotice
          type="error"
          showIcon
          className="mb-4"
          title="仪表台统计加载失败"
          description={error}
        />
      ) : null}

      {notSetUp || partiallySetUp ? (
        <PlatformNotice
          type={partiallySetUp ? 'warning' : 'info'}
          showIcon
          className="mb-4"
          title={
            partiallySetUp
              ? `「${missingTables[0]}」尚未绑定或同步，相关统计暂为 0`
              : '尚未完成飞书数据绑定'
          }
          description={
            partiallySetUp
              ? `请在「飞书设置」确认已发现「${missingTables[0]}」数据表并绑定到对应页面后同步。若发现不到该表，通常是飞书多维表格开启了高级权限而行政应用未被授权该表，需要表格管理员在高级权限中为该应用开放阅读权限。`
              : '请在「飞书设置」保存行政飞书应用凭证，添加多维表格数据入口并同步，再把「物品清单」「领用记录」两个页面绑定到对应数据表；绑定后统计会自动出现。'
          }
          action={
            <Button size="small" icon={<SettingOutlined />} href="/admin/settings/feishu">
              前往飞书设置
            </Button>
          }
        />
      ) : null}

      {stats ? (
        <>
          <div className="mb-4 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              label="物品品类"
              value={formatQuantity(stats.item_categories)}
              accent={token.colorWarning}
            />
            <MetricCard
              label="物品总价"
              value={formatMoney(stats.item_total_value)}
              accent={token.colorPrimary}
            />
            <MetricCard
              label="物品总数"
              value={formatQuantity(stats.item_total_count)}
              accent={token.colorPrimary}
            />
            <MetricCard
              label="已领用物品总数"
              value={formatQuantity(stats.requisitioned_total)}
              accent={token.colorPrimary}
              hint="状态为「已领用」的领用单数量合计"
            />
          </div>

          {/* 物品维度有 30+ 根柱子，任何屏宽都单列展示，保证横轴物品名可读 */}
          <div className="mb-4 grid grid-cols-1 gap-4">
            <ChartCard
              title="物品库存情况"
              seriesName="物品总数"
              data={stats.inventory_by_item}
              color={token.colorPrimary}
            />
            <ChartCard
              title="物品领取分析"
              seriesName="领用数量"
              data={stats.requisition_by_item}
              color={token.colorPrimary}
              note="不含已作废"
            />
            <ChartCard
              title="领用物品总价分布"
              seriesName="总金额"
              data={stats.value_by_item}
              color={token.colorPrimary}
              money
            />
          </div>

          <ChartCard
            title="员工领用统计"
            seriesName="领用数量"
            data={stats.requisition_by_employee}
            color={token.colorPrimary}
            height={360}
            note="按申请人，不含已作废"
          />
        </>
      ) : null}
    </main>
  )
}
