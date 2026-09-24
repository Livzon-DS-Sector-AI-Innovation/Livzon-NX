'use client'

import { useMemo, useState } from 'react'
import { App, Button, Descriptions, Drawer, Empty, Modal, Select, Spin, Table, Tag } from 'antd'
import type { TableColumnsType } from 'antd'
import {
  ClockCircleOutlined,
  DatabaseOutlined,
  FieldTimeOutlined,
  InboxOutlined,
  RightOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import { graphic } from 'echarts'
import type { EChartsOption } from 'echarts'
import { useQuery } from '@tanstack/react-query'
import {
  fetchWarehouseInspectionProgressOverview,
  fetchWarehouseRecordDetail,
} from '@/lib/api/client/warehouse'
import { formatDetailDisplayValue } from '@/lib/format/warehouse'
import { renderInspectionCycleBlock } from './inspectionCycle'
import type {
  WarehouseInspectionOverview,
  WarehouseInspectionPendingItem,
  WarehouseRecordDetail,
} from '@/types/warehouse'

const BRAND = '#5645d4'
const QUALIFIED_COLOR = '#52c41a'
const UNQUALIFIED_COLOR = '#ff4d4f'

const DAY_OPTIONS = [
  { label: '近 7 天', value: 7 },
  { label: '近 30 天', value: 30 },
  { label: '近 90 天', value: 90 },
]

function formatDuration(hours?: number | null): string {
  if (hours == null) {
    return '—'
  }
  if (hours < 48) {
    return `${hours.toFixed(1)} 小时`
  }
  return `${(hours / 24).toFixed(1)} 天`
}

function formatDateTime(value?: string | null): string {
  if (!value) {
    return '—'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString('zh-CN', { hour12: false })
}

interface MiniStatProps {
  icon: React.ReactNode
  label: string
  value: string
  hint?: string
  color: string
  onClick?: () => void
}

function MiniStat({ icon, label, value, hint, color, onClick }: MiniStatProps) {
  return (
    <div
      className={`rounded-xl border border-[var(--color-hairline)] bg-white p-4 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg${onClick ? ' cursor-pointer' : ''}`}
      onClick={onClick}
    >
      <div className="flex items-start gap-3">
        <div
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-[18px] text-white"
          style={{ background: `linear-gradient(135deg, ${color}, ${color}bb)` }}
        >
          {icon}
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[12px] font-medium text-[var(--color-steel)]">{label}</div>
          <div className="mt-1 text-[20px] font-bold leading-none" style={{ color }}>
            {value}
          </div>
          {onClick ? (
            <div className="mt-1 truncate text-[11px] text-[var(--color-primary)]">点击查看明细</div>
          ) : hint ? (
            <div className="mt-1 truncate text-[11px] text-[var(--color-muted)]">{hint}</div>
          ) : null}
        </div>
      </div>
    </div>
  )
}

function dailyChartOption(overview: WarehouseInspectionOverview): EChartsOption {
  const daily = overview.daily ?? []
  return {
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#ffffff',
      borderColor: '#ececf4',
      borderWidth: 1,
      textStyle: { color: '#333', fontSize: 12 },
      extraCssText: 'box-shadow:0 6px 20px rgba(26,42,82,0.14);border-radius:10px;',
    },
    legend: { top: 0, textStyle: { fontSize: 11, color: '#5a5f73' } },
    grid: { left: 48, right: 52, top: 36, bottom: 56 },
    xAxis: {
      type: 'category',
      data: daily.map((item) => item.date.slice(5)),
      axisLabel: { fontSize: 10, rotate: 45, color: '#8a8fa3' },
      axisLine: { lineStyle: { color: '#e3e5ef' } },
      axisTick: { show: false },
    },
    yAxis: [
      {
        type: 'value',
        name: '批次数',
        minInterval: 1,
        axisLabel: { color: '#8a8fa3' },
        splitLine: { lineStyle: { type: 'dashed', color: '#eef0f7' } },
      },
      {
        type: 'value',
        name: '平均周期(小时)',
        axisLabel: { color: '#8a8fa3' },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: '合格',
        type: 'bar',
        stack: 'done',
        data: daily.map((item) => item.qualified),
        itemStyle: { color: QUALIFIED_COLOR, borderRadius: [0, 0, 0, 0] },
        barMaxWidth: 18,
      },
      {
        name: '不合格',
        type: 'bar',
        stack: 'done',
        data: daily.map((item) => item.unqualified),
        itemStyle: {
          color: new graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: UNQUALIFIED_COLOR },
            { offset: 1, color: `${UNQUALIFIED_COLOR}99` },
          ]),
          borderRadius: [4, 4, 0, 0],
        },
        barMaxWidth: 18,
      },
      {
        name: '平均检验周期',
        type: 'line',
        yAxisIndex: 1,
        smooth: true,
        symbol: 'circle',
        symbolSize: 5,
        data: daily.map((item) => item.avg_hours ?? null),
        lineStyle: { width: 2.5, color: BRAND },
        itemStyle: { color: BRAND, borderColor: '#fff', borderWidth: 1.5 },
        connectNulls: true,
      },
    ],
  }
}

const PENDING_COLUMNS: TableColumnsType<WarehouseInspectionPendingItem> = [
  { title: '名称', dataIndex: 'name', key: 'name', ellipsis: true },
  { title: '批号', dataIndex: 'batch', key: 'batch', width: 110, render: (v) => v || '—' },
  {
    title: '入库日期',
    dataIndex: 'inbound_date',
    key: 'inbound_date',
    width: 110,
    render: (v) => v || '—',
  },
  {
    title: '已等待',
    dataIndex: 'waited_hours',
    key: 'waited_hours',
    width: 100,
    render: (v: number | null) => (
      <span className={v != null && v > 24 * 7 ? 'font-semibold text-[#ff4d4f]' : ''}>
        {formatDuration(v)}
      </span>
    ),
  },
]

/**
 * 仓储仪表盘的「近期检验进度」面板：
 * 当前待验 / 近 N 天完成检验 / 检验周期分布 / 最久待验 Top5。
 * 待验卡片与待验列表行可下钻查看批次记录详情（飞书全字段 + 检验周期）。
 * 接口失败时静默隐藏（不影响仪表盘主数据）。
 */
export function WarehouseInspectionProgressPanel({ scope }: { scope: 'raw' | 'product' }) {
  const { message } = App.useApp()
  const [days, setDays] = useState(30)
  const { data, refetch } = useQuery({
    queryKey: ['warehouse-inspection-progress', scope, days],
    queryFn: () => fetchWarehouseInspectionProgressOverview(scope, days),
    staleTime: 5 * 60 * 1000,
    retry: false,
  })

  // ── 待验下钻：全量列表抽屉 + 单条记录详情弹窗 ─────────────────
  const [listOpen, setListOpen] = useState(false)
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailData, setDetailData] = useState<WarehouseRecordDetail | null>(null)

  const openPendingList = () => {
    // 下钻时绕过前端 5 分钟新鲜窗口主动拉新（后端仍有进程缓存）
    void refetch()
    setListOpen(true)
  }

  const openRecordDetail = async (item: WarehouseInspectionPendingItem) => {
    if (!item.page_key || !item.record_id) {
      return
    }
    setDetailOpen(true)
    setDetailLoading(true)
    setDetailData(null)
    try {
      const detail = await fetchWarehouseRecordDetail(item.page_key, item.record_id)
      setDetailData(detail)
    } catch (error) {
      const reason = error instanceof Error ? error.message : '未知错误'
      message.error(`详情加载失败：${reason}`)
      setDetailOpen(false)
    } finally {
      setDetailLoading(false)
    }
  }

  const pendingColumns = useMemo(() => {
    if (scope === 'product') {
      // 成品口径 name 即产品名称，不再重复产品列
      return PENDING_COLUMNS as TableColumnsType<WarehouseInspectionPendingItem>
    }
    return [
      PENDING_COLUMNS[0],
      PENDING_COLUMNS[1],
      { title: '物料类别', dataIndex: 'category', key: 'category', width: 96, render: (v: string | null) => v || '—' },
      ...PENDING_COLUMNS.slice(2),
    ] as TableColumnsType<WarehouseInspectionPendingItem>
  }, [scope])

  // 数据缺失或结构不完整（旧版本/异常响应/测试桩返回非对象）时静默隐藏
  if (!data || !data.current || !data.window) {
    return null
  }

  const { current, window: win, stages, oldest_pending } = data
  // 旧后端未返回全量列表时兜底 Top5，保证卡片数字与列表一致
  const pendingRows = data.pending_items ?? oldest_pending ?? []
  const ledgerLink =
    scope === 'raw'
      ? '/warehouse/materials/inbound-ledger'
      : '/warehouse/product/inbound-detail'
  const pendingRowKey = (record: WarehouseInspectionPendingItem) =>
    record.record_id ?? `${record.name}-${record.batch ?? ''}-${record.inbound_date ?? ''}`
  const pendingRowProps = (record: WarehouseInspectionPendingItem) => ({
    style: { cursor: 'pointer' },
    onClick: () => void openRecordDetail(record),
  })

  return (
    <section className="mt-4 overflow-hidden rounded-xl border border-[var(--color-hairline)] bg-white shadow-sm">
      <div className="flex flex-wrap items-center gap-2 border-b border-[var(--color-hairline)] px-4 py-3">
        <span
          className="h-4 w-1 rounded-full"
          style={{ background: 'linear-gradient(#5645d4 0%, #13c2c2 100%)' }}
        />
        <span className="text-[14px] font-semibold text-[var(--color-charcoal)]">
          近期检验进度{data.scope_label ? ` · ${data.scope_label}` : ''}
        </span>
        <Tag color="purple" variant="filled">
          统计自 {data.start_date}
        </Tag>
        <div className="ml-auto">
          <Select
            size="small"
            value={days}
            options={DAY_OPTIONS}
            onChange={setDays}
            style={{ width: 100 }}
          />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2 xl:grid-cols-4">
        <MiniStat
          icon={<InboxOutlined />}
          label="当前待验批次"
          value={String(current.pending_count)}
          hint={`平均已等待 ${formatDuration(current.pending_avg_hours)}`}
          color="#faad14"
          onClick={openPendingList}
        />
        <MiniStat
          icon={<SafetyCertificateOutlined />}
          label={`近 ${win.days} 天完成检验`}
          value={String(win.completed_count)}
          hint={`合格 ${win.qualified_count} · 不合格 ${win.unqualified_count}`}
          color="#52c41a"
        />
        <MiniStat
          icon={<ClockCircleOutlined />}
          label="平均检验周期"
          value={formatDuration(win.avg_hours)}
          hint={`中位数 ${formatDuration(win.median_hours)} · P90 ${formatDuration(win.p90_hours)}`}
          color={BRAND}
        />
        <MiniStat
          icon={<FieldTimeOutlined />}
          label={scope === 'product' ? '分段平均时长' : '最长检验周期'}
          value={
            scope === 'product'
              ? `入库→待验 ${formatDuration(stages?.inbound_to_pending_avg_hours)}`
              : formatDuration(win.max_hours)
          }
          hint={
            scope === 'product'
              ? `待验→结果 ${formatDuration(stages?.pending_to_result_avg_hours)}`
              : `最长待验 ${formatDuration(current.pending_max_hours)}`
          }
          color="#13c2c2"
        />
      </div>

      <div className="grid grid-cols-1 gap-4 px-4 pb-4 xl:grid-cols-5">
        <div className="xl:col-span-3">
          <div className="mb-2 text-[13px] font-medium text-[var(--color-charcoal)]">
            每日完成检验数与平均周期
          </div>
          {win.completed_count === 0 && current.pending_count === 0 ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="暂无检验记录（统计自功能上线日起累计）"
            />
          ) : (
            <ReactECharts option={dailyChartOption(data)} style={{ height: 260 }} notMerge lazyUpdate />
          )}
        </div>
        <div className="xl:col-span-2">
          <div className="mb-2 text-[13px] font-medium text-[var(--color-charcoal)]">
            最久待验 Top 5
            <span className="ml-2 text-[11px] font-normal text-[var(--color-muted)]">
              点击行可查看批次详情
            </span>
          </div>
          <Table<WarehouseInspectionPendingItem>
            columns={pendingColumns}
            dataSource={oldest_pending ?? []}
            rowKey={pendingRowKey}
            onRow={pendingRowProps}
            size="small"
            pagination={false}
            locale={{
              emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无待验批次" />,
            }}
          />
        </div>
      </div>
      <div className="border-t border-[var(--color-hairline)] px-4 py-2 text-[11px] text-[var(--color-muted)]">
        数据生成于 {formatDateTime(data.generated_at)}；检验周期 = 入库日期 → 检测结果/质量状态出结果时刻（同步间隔约 10 分钟）
      </div>

      {/* 待验批次全量列表抽屉（点击「当前待验批次」卡片打开） */}
      <Drawer
        title={`当前待验批次（共 ${pendingRows.length} 条）`}
        open={listOpen}
        onClose={() => setListOpen(false)}
        size={720}
        extra={
          <Button
            type="link"
            href={ledgerLink}
            target="_blank"
            rel="noreferrer"
            icon={<DatabaseOutlined />}
          >
            前往台账查看
          </Button>
        }
      >
        <div className="mb-2 text-[12px] text-[var(--color-muted)]">
          按已等待时长降序；点击行可查看该批次的完整记录详情与检验进度周期
        </div>
        <Table<WarehouseInspectionPendingItem>
          columns={pendingColumns}
          dataSource={pendingRows}
          rowKey={pendingRowKey}
          onRow={pendingRowProps}
          size="small"
          pagination={
            pendingRows.length > 10
              ? {
                  pageSize: 10,
                  showTotal: (total) => `共 ${total} 条`,
                }
              : false
          }
          locale={{
            emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无待验批次" />,
          }}
        />
      </Drawer>

      {/* 待验批次记录详情（飞书全字段 + 检验周期，只读） */}
      <Modal
        open={detailOpen}
        onCancel={() => setDetailOpen(false)}
        width={820}
        footer={null}
        title={
          <span className="flex items-center gap-2">
            批次记录详情
            {detailData ? (
              <span className="text-[12px] font-normal text-[var(--color-muted)]">
                {detailData.record_id}
              </span>
            ) : null}
            <RightOutlined className="text-[12px] text-[var(--color-muted)]" />
            <span className="text-[12px] font-normal text-[var(--color-muted)]">只读</span>
          </span>
        }
      >
        <Spin spinning={detailLoading}>
          {detailData ? (
            <>
              <Descriptions bordered size="small" column={2} className="wh-detail-desc">
                {detailData.fields.map((field) => (
                  <Descriptions.Item
                    key={field.field_name}
                    label={
                      <span className="break-all text-[12px]">{field.field_name}</span>
                    }
                  >
                    <span className="break-all text-[13px]">
                      {formatDetailDisplayValue(field)}
                    </span>
                  </Descriptions.Item>
                ))}
              </Descriptions>
              {renderInspectionCycleBlock(detailData.inspection_cycle)}
            </>
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="加载中或记录不存在" />
          )}
        </Spin>
      </Modal>
    </section>
  )
}

export default WarehouseInspectionProgressPanel
