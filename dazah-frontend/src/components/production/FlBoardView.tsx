'use client'

// FL 氟苯尼考预混剂生产看板：合成预混工艺无发酵工段，以批次工序流转
// 为主轴。口径（入库确认为准）：
// - 计划 = 排产多维表「N月排产」（飞书同步，日期为预填计划值）
// - 实际入库 = 仓储「入库台账（明细）」（入库标签批号匹配，仅计已勾
//   「入库确认」的行）
// - 工序流转 = 锚点（当前月=现在 / 历史月=月末）前后各 2 天滚动窗口：
//   在制/待入库确认/滞留常驻，已入库保留 2 天，待投料预告进窗
// 每张卡标题右上角的 * 悬停显示该卡数据来源与口径。

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Card,
  Col,
  Empty,
  Row,
  Statistic,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import { getFlBoard } from '@/actions/production'
import type { ApiResponse, FlBoard, FlBoardBatch } from '@/types/production'
import {
  PRODUCTION_PAGE_KEYS,
  useProductionPermissions,
} from './useProductionPermissions'
import BatchProgressBar from './batch-progress-bar'
import SyncSettingsButton from './SyncSettingsButton'

const { Text } = Typography

const REFRESH_INTERVAL_MS = 5 * 60 * 1000
const FL_PRODUCT_NAME = '2%氟苯尼考预混剂'

const DASH = '--'

const fmtKg = (kg: number | null | undefined) =>
  kg == null
    ? DASH
    : `${kg.toLocaleString('zh-CN', {
        minimumFractionDigits: 0,
        maximumFractionDigits: 2,
      })} kg`

const fmtDate = (value: string | null | undefined) =>
  value ? value.slice(5).replace('-', '/') : DASH

const STAGE_COLOR: Record<string, string> = {
  order: 'default',
  pick: 'default',
  charge: 'processing',
  mix: 'processing',
  pack: 'cyan',
  inspection: 'geekblue',
  inbound: 'success',
}

const STATE_COLOR: Record<string, string> = {
  upcoming: 'default',
  running: 'processing',
  confirm_pending: 'warning',
  stalled: 'error',
  inbound: 'success',
}

/** 卡片标题右上角的数据来源角标：悬停显示来源与口径说明 */
function SourceMark({ content }: { content: string }) {
  return (
    <Tooltip
      title={
        <div style={{ whiteSpace: 'pre-line', maxWidth: 340 }}>{content}</div>
      }
    >
      <sup
        data-testid="fl-source-mark"
        style={{
          color: 'var(--color-primary)',
          cursor: 'help',
          fontSize: 12,
          marginInlineStart: 2,
        }}
      >
        *
      </sup>
    </Tooltip>
  )
}

interface Props {
  /** 概览月份 YYYY-MM（空串按当月） */
  month: string
  /** 页面「立即刷新」驱动的刷新信号 */
  refreshKey: number
}

export default function FlBoardView({ month, refreshKey }: Props) {
  const permissions = useProductionPermissions(PRODUCTION_PAGE_KEYS.overview)
  const [board, setBoard] = useState<FlBoard | null>(null)
  const [boardMessage, setBoardMessage] = useState('')
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      const res = await getFlBoard(month || undefined)
      const payload = res as ApiResponse<FlBoard>
      if (payload.code === 200 && payload.data) {
        setBoard(payload.data)
        setBoardMessage('')
      } else {
        setBoardMessage(payload.message || '看板数据加载失败')
      }
    } catch {
      setBoardMessage('看板数据加载失败')
    } finally {
      setLoading(false)
    }
  }, [month])

  useEffect(() => {
    setLoading(true) // eslint-disable-line react-hooks/set-state-in-effect -- 月份/刷新信号切换时重置加载态，与概览页既有模式一致
    void load()
    const timer = setInterval(() => void load(), REFRESH_INTERVAL_MS)
    return () => clearInterval(timer)
  }, [load, refreshKey])

  const flow = board?.flow ?? []
  const monthBatches = board?.month_batches ?? []
  const recentCompleted = board?.recent_completed ?? []
  const hasData = monthBatches.length > 0 || flow.length > 0
  const periodLabel = board?.period.label ?? ''
  const monthLabel = board ? `${Number(board.month.slice(5))}月` : ''

  const sourceNotes = useMemo(() => {
    const detailTable = `仓储「入库台账（明细）」（飞书同步，约 10 分钟延迟）\n区间：扎帐月 ${periodLabel}（按实际入库日期）\n口径：仅计「入库确认」已勾的行；批次数按去重入库标签批号`
    return {
      planned: `产销计划（生产计划模块 · 飞书同步）\n取数：${monthLabel}自然月内计划日期的行，产品 = 2%氟苯尼考预混剂，车间不含"发酵"，合计计划产量（KG）\n当月无该产品计划行时显示 --`,
      plannedBatches: `排产多维表「氟苯尼考预混剂排产 · N月排产」（飞书同步）\n取数：按批号 YYMM 归组到${monthLabel}，统计该月全部批次（含未投料）`,
      inboundBatches: detailTable,
      inboundKg: `${detailTable}\n数量：已确认行"入库量"合计，实际入库值（与排产表规格重量名目值不同）`,
      completion: `算式：实际入库产量（仓储已确认） ÷ 计划产量（产销计划）\n保留两位小数；计划为空时显示 --\n大于 100% 表示实际入库超过产销计划`,
      inProgress: `排产多维表 + 仓储入库台账联合判定\n口径：${monthLabel}已到投料开始时刻、且台账中无该批号已确认记录的批次\n= 在制 + 待入库确认 + 滞留（明细见下方工序流转表）`,
      flow: `排产多维表（飞书同步，每天 8:00–20:00 每小时 + 手动）+ 仓储入库台账\n窗口：锚点${board?.is_current_month ? '（现在）' : '（所选月末）'}前后各 2 天；在制/待入库确认/滞留常驻，已入库保留 2 天，待投料预告进窗\n状态：在制=已投料未到计划入库日；待入库确认=台账已登记未勾确认；滞留=已过计划入库日且台账无登记\n当前工序按排产计划时间推导（指令→领料→投料→混合→包装→请检→入库）`,
      monthBatches: `排产多维表 + 仓储入库台账\n仅列${monthLabel}已确认入库的批次，按实际入库日期倒序\n规格重量(kg) 为排产名目值（如 1980），非实际入库`,
      recent: `仓储「入库台账（明细）」已确认批次\n全产线按实际入库日期倒序取前 10 批\n规格重量(kg) 为排产名目值`,
    }
  }, [periodLabel, monthLabel, board])

  const kpiCards = useMemo(
    () => [
      {
        key: 'planned-batches',
        title: '计划批次',
        note: sourceNotes.plannedBatches,
        value: board ? String(board.planned_batches) : DASH,
        sub: '当月排产表批次总数',
      },
      {
        key: 'planned',
        title: '本月计划产量',
        note: sourceNotes.planned,
        value: board?.planned_kg != null ? fmtKg(board.planned_kg) : DASH,
        sub: board ? `${monthLabel}产销计划` : '',
      },
      {
        key: 'inbound-batches',
        title: '本月入库批次',
        note: sourceNotes.inboundBatches,
        value: board ? String(board.inbound_batches) : DASH,
        sub: '仓储入库 · 扎帐月 · 已确认',
      },
      {
        key: 'inbound-kg',
        title: '本月入库产量',
        note: sourceNotes.inboundKg,
        value: board?.inbound_kg != null ? fmtKg(board.inbound_kg) : DASH,
        sub: '仓储入库 · 实际值',
      },
      {
        key: 'completion',
        title: '计划完成率',
        note: sourceNotes.completion,
        value:
          board?.completion_rate != null
            ? `${board.completion_rate.toFixed(2)}%`
            : DASH,
        sub: '实际入库产量 ÷ 计划产量',
      },
      {
        key: 'in-progress',
        title: '在制批次',
        note: sourceNotes.inProgress,
        value: board ? String(board.in_progress_count) : DASH,
        sub: `${monthLabel}已投料未确认入库`,
      },
    ],
    [board, monthLabel, sourceNotes],
  )

  const flowColumns = [
    {
      title: '批次号',
      dataIndex: 'batch_no',
      key: 'batch_no',
      width: 120,
      render: (v: string) => <Text strong>{v}</Text>,
    },
    {
      title: '状态',
      dataIndex: 'state',
      key: 'state',
      width: 110,
      render: (state: string, record: FlBoardBatch) => (
        <Tag color={STATE_COLOR[state] ?? 'default'}>{record.state_label}</Tag>
      ),
    },
    {
      title: '当前工序',
      dataIndex: 'stage_label',
      key: 'stage',
      width: 90,
      render: (label: string, record: FlBoardBatch) => (
        <Tag color={STAGE_COLOR[record.stage_key] ?? 'default'}>{label}</Tag>
      ),
    },
    { title: '指令', dataIndex: 'order_date', key: 'order', width: 80, render: fmtDate },
    {
      title: '投料',
      key: 'charge',
      width: 140,
      render: (_: unknown, record: FlBoardBatch) =>
        record.charge_date
          ? `${fmtDate(record.charge_date)}${record.charge_time ? ` ${record.charge_time}` : ''}`
          : DASH,
    },
    { title: '包装(计划)', dataIndex: 'pack_date', key: 'pack', width: 100, render: fmtDate },
    { title: '入库(计划)', dataIndex: 'planned_inbound_date', key: 'planned_inbound', width: 100, render: fmtDate },
    { title: '入库(实际)', dataIndex: 'actual_inbound_date', key: 'actual_inbound', width: 100, render: fmtDate },
  ]

  const monthColumns = [
    {
      title: '批次号',
      dataIndex: 'batch_no',
      key: 'batch_no',
      width: 130,
      render: (v: string) => <Text strong>{v}</Text>,
    },
    { title: '序号', dataIndex: 'seq', key: 'seq', width: 70, render: (v: number | null) => v ?? DASH },
    { title: '指令', dataIndex: 'order_date', key: 'order', width: 90, render: fmtDate },
    { title: '投料', dataIndex: 'charge_date', key: 'charge', width: 90, render: fmtDate },
    { title: '包装(计划)', dataIndex: 'pack_date', key: 'pack', width: 100, render: fmtDate },
    { title: '入库(实际)', dataIndex: 'actual_inbound_date', key: 'actual_inbound', width: 100, render: fmtDate },
    { title: '规格', dataIndex: 'spec', key: 'spec', width: 150, ellipsis: true },
    {
      title: '规格重量(kg)',
      dataIndex: 'pack_weight_kg',
      key: 'weight',
      width: 120,
      align: 'right' as const,
      render: (v?: number | null) =>
        v == null ? DASH : v.toLocaleString('zh-CN', { maximumFractionDigits: 2 }),
    },
  ]

  const recentColumns = [
    {
      title: '批次号',
      dataIndex: 'batch_no',
      key: 'batch_no',
      render: (v: string) => <Text strong>{v}</Text>,
    },
    { title: '入库(实际)', dataIndex: 'actual_inbound_date', key: 'actual_inbound', render: fmtDate },
    {
      title: '规格重量(kg)',
      dataIndex: 'pack_weight_kg',
      key: 'weight',
      align: 'right' as const,
      render: (v?: number | null) =>
        v == null ? DASH : v.toLocaleString('zh-CN', { maximumFractionDigits: 2 }),
    },
  ]

  return (
    <>
      {/* 同步入口 + 数据来源说明：FL 无发酵排产表，批次数据来自多维表月表同步 */}
      <Card
        variant="borderless"
        className="shadow-sm"
        styles={{ body: { padding: '8px 16px' } }}
      >
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <Text type="secondary" style={{ fontSize: 12 }}>
            合成预混工艺，无发酵工段；计划=排产多维表，实际入库=仓储「入库台账（明细）」
            {board && hasData
              ? `，最新数据 ${board.generated_at.slice(5, 16).replace('T', ' ')}`
              : ''}
            ；卡片标题 * 悬停查看数据来源
          </Text>
          {permissions.canSync && (
            <SyncSettingsButton
              productName={FL_PRODUCT_NAME}
              syncTarget="fl_batch"
              pageKey={PRODUCTION_PAGE_KEYS.overview}
              tableIdOptional
              tableIdHelp="按月分表自动同步：留空即按表名「N月排产」自动发现全部月表"
              onSync={() => void load()}
            />
          )}
        </div>
      </Card>

      {boardMessage && (
        <Alert type="error" showIcon message={boardMessage} />
      )}

      {!loading && !hasData && !boardMessage ? (
        <Card variant="borderless" className="shadow-sm">
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <span style={{ fontSize: 14 }}>
                尚未同步到批次数据
                <br />
                <Text type="secondary" style={{ fontSize: 12 }}>
                  请在上方「同步设置」配置飞书多维表并触发同步；每小时 8:00–20:00 自动同步
                </Text>
              </span>
            }
          />
        </Card>
      ) : (
        <>
          {/* KPI 卡片区 */}
          <Row gutter={[12, 12]}>
            {kpiCards.map((card) => (
              <Col key={card.key} xs={12} md={8} xl={4}>
                <Card
                  variant="borderless"
                  className="shadow-sm h-full"
                  styles={{ body: { padding: '10px 14px' } }}
                >
                  <Statistic
                    title={
                      <span style={{ fontSize: 12 }}>
                        {card.title}
                        <SourceMark content={card.note} />
                      </span>
                    }
                    value={card.value}
                    styles={{ content: { fontSize: 26, fontWeight: 600 } }}
                  />
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    {card.sub}
                  </Text>
                </Card>
              </Col>
            ))}
          </Row>

          {/* 生产进度：箭头进度条（与发酵看板同组件），产量口径=实际入库÷计划 */}
          <Card
            variant="borderless"
            className="shadow-sm"
            styles={{ body: { padding: '12px 20px' } }}
          >
            <div className="flex items-center gap-2 flex-wrap" style={{ marginBottom: 4 }}>
              <Text strong>
                {board ? `${monthLabel}生产进度` : '生产进度'}
                <SourceMark
                  content={`批次数量口径：排产表 + 入库台账——已入库（已确认）/ 在制（含待确认与滞留）/ 未投料，占当月排产总批次比例\n产量(kg)口径：仓储实际入库（已确认）÷ 产销计划\n切换右上角按钮换口径`}
                />
              </Text>
              {!board?.is_current_month && <Tag color="orange">历史月</Tag>}
            </div>
            <BatchProgressBar
              doneCount={board?.progress.by_batches.inbound ?? 0}
              pendingCount={0}
              runningCount={board?.progress.by_batches.in_progress ?? 0}
              idleCount={board?.progress.by_batches.not_started ?? 0}
              doneYieldKg={board?.progress.by_kg.completed_kg ?? null}
              plannedCapacityKg={board?.progress.by_kg.planned_kg ?? null}
              historical={!board?.is_current_month}
              labels={{ done: '已入库', running: '在制', idle: '未投料' }}
              hideZeroLegend
            />
          </Card>

          {/* 工序流转实时状态：锚点 ±2 天滚动窗口 */}
          <Card
            title={
              <span className="flex items-center gap-2 flex-wrap">
                工序流转实时状态
                <SourceMark content={sourceNotes.flow} />
                <Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
                  {board?.is_current_month ? '现在' : '月末'}前后 2 天滚动窗口；
                  待确认/滞留常驻
                </Text>
              </span>
            }
            variant="borderless"
            className="shadow-sm"
            styles={{ body: { padding: 8 } }}
          >
            <Table
              rowKey="batch_no"
              size="small"
              loading={loading}
              columns={flowColumns}
              dataSource={flow}
              pagination={false}
              scroll={{ x: 1000 }}
              locale={{
                emptyText: '窗口内暂无批次流转（在制/待确认/滞留批次会常驻显示）',
              }}
            />
          </Card>

          {/* 当月批次明细 + 最近完成批次 */}
          <Row gutter={[12, 12]}>
            <Col xs={24} lg={16}>
              <Card
                title={
                  <span className="flex items-center gap-2">
                    {board ? `${board.month} 批次明细` : '批次明细'}
                    <SourceMark content={sourceNotes.monthBatches} />
                  </span>
                }
                variant="borderless"
                className="shadow-sm h-full"
                styles={{ body: { padding: 8 } }}
              >
                <Table
                  rowKey="batch_no"
                  size="small"
                  loading={loading}
                  columns={monthColumns}
                  dataSource={monthBatches}
                  pagination={{ pageSize: 12, hideOnSinglePage: true, size: 'small' }}
                  scroll={{ x: 950 }}
                  locale={{ emptyText: '本月暂无已确认入库的批次' }}
                />
              </Card>
            </Col>
            <Col xs={24} lg={8}>
              <Card
                title={
                  <span className="flex items-center gap-2">
                    最近完成批次
                    <SourceMark content={sourceNotes.recent} />
                  </span>
                }
                variant="borderless"
                className="shadow-sm h-full"
                styles={{ body: { padding: 8 } }}
              >
                <Table
                  rowKey="batch_no"
                  size="small"
                  loading={loading}
                  columns={recentColumns}
                  dataSource={recentCompleted}
                  pagination={false}
                  locale={{ emptyText: '暂无已确认入库批次' }}
                />
              </Card>
            </Col>
          </Row>
        </>
      )}
    </>
  )
}
