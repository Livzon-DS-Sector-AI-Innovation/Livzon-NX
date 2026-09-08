'use client'

// 发酵车间生产实时看板（生产管理概览页，一期：计划驱动）
// 数据源：最新排产 Excel 存档（当前扎帐周期块）+ 人工检修标注。
// 实际完成/收率/合格率等指标待实际数据接入后启用（当前显示 --）。

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  Card,
  Row,
  Col,
  Typography,
  Button,
  Tag,
  Table,
  App,
  Modal,
  Input,
  Statistic,
  Empty,
  Space,
} from 'antd'
import {
  ScheduleOutlined,
  SyncOutlined,
  ToolOutlined,
  AlertOutlined,
  ArrowRightOutlined,
  ShopOutlined,
} from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import {
  getFermentationBoard,
  markTankMaintenance,
  removeTankMaintenance,
} from '@/actions/production'
import type { FermentationBoard, BoardTank } from '@/types/production'

const { Title, Text } = Typography

// 车间工段首页：与侧边菜单「批次管理 → 车间」保持一致，只列实际存在页面的车间。
const workshopItems = [
  {
    key: '/production/batches/workshop/101-1',
    title: '101一车间（菌种）',
    description: '摇瓶种子制备全流程',
    color: '#52c41a',
  },
  {
    key: '/production/batches/workshop/101-2',
    title: '101二车间',
    description: '发酵数据（林可霉素/霉酚酸/他汀类）',
    color: '#08979c',
  },
  {
    key: '/production/batches/workshop/102-1',
    title: '102一车间',
    description: '发酵数据（多拉菌素）',
    color: '#1d39c4',
  },
  {
    key: '/production/batches/workshop/103/phenylalanine',
    title: '103车间 · 苯丙氨酸',
    description: '发酵数据（L-苯丙氨酸）',
    color: '#531dab',
  },
  {
    key: '/production/batches/workshop/103/lovastatin',
    title: '103车间 · 洛伐他汀/美伐他汀',
    description: '发酵数据',
    color: '#c41d7f',
  },
  {
    key: '/production/batches/workshop/201-2',
    title: '201二车间 · 霉酚酸（MC）',
    description: '提炼至混粉入库',
    color: '#d4380d',
  },
  {
    key: '/production/batches/workshop/201-3',
    title: '201三车间 · 多拉菌素（DR）',
    description: '提炼至混粉入库',
    color: '#fa8c16',
  },
  {
    key: '/production/batches/workshop/202',
    title: '202车间',
    description: '停产中，暂无生产数据',
    color: '#8c8c8c',
  },
  {
    key: '/production/batches/workshop/203',
    title: '203车间 · L-苯丙氨酸（FA）',
    description: '发酵放罐至精制回收',
    color: '#237804',
  },
]

const REFRESH_INTERVAL_MS = 5 * 60 * 1000

function fmtDateTime(value?: string | null): string {
  if (!value) return '--'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '--'
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

function fmtShort(value?: string | null): string {
  if (!value) return '-'
  // 纯日期字符串（如计划放罐日期）直接截取，避免 Date 按 UTC 解析产生时区偏移
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  if (dateOnly) return `${dateOnly[2]}-${dateOnly[3]}`
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '-'
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

const STATUS_META: Record<string, { label: string; color: string }> = {
  running: { label: '运行中', color: 'success' },
  dumping: { label: '放罐中', color: 'processing' },
  idle: { label: '空闲待投料', color: 'default' },
  maintenance: { label: '检修维护', color: 'warning' },
  dumped: { label: '已放罐', color: 'default' },
}

export default function ProductionDashboard() {
  const router = useRouter()
  const { message } = App.useApp()
  const [board, setBoard] = useState<FermentationBoard | null>(null)
  const [boardMessage, setBoardMessage] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [clock, setClock] = useState(() => fmtDateTime(new Date().toISOString()))
  const [maintModalOpen, setMaintModalOpen] = useState(false)
  const [maintTank, setMaintTank] = useState<BoardTank | null>(null)
  const [maintReason, setMaintReason] = useState('')

  const loadBoard = useCallback(async () => {
    try {
      const res = await getFermentationBoard()
      if (res.code === 200) {
        setBoard(res.data)
        setBoardMessage(res.data ? '' : res.message || '')
      } else {
        setBoardMessage(res.message || '看板数据加载失败')
      }
    } catch {
      setBoardMessage('看板数据加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadBoard() // eslint-disable-line react-hooks/set-state-in-effect -- 看板初始加载，与 201-2 页面既有模式一致
    const timer = setInterval(() => void loadBoard(), REFRESH_INTERVAL_MS)
    return () => clearInterval(timer)
  }, [loadBoard])

  useEffect(() => {
    const timer = setInterval(
      () => setClock(fmtDateTime(new Date().toISOString())),
      1000,
    )
    return () => clearInterval(timer)
  }, [])

  const submitMaintenance = async () => {
    if (!maintTank || !maintReason.trim()) {
      message.warning('请填写检修原因')
      return
    }
    const res = await markTankMaintenance(maintTank.tank_no, maintReason.trim())
    if (res.code === 200) {
      message.success(`${maintTank.tank_no} 已标记检修`)
      setMaintModalOpen(false)
      setMaintReason('')
      await loadBoard()
    } else {
      message.error(res.message || '标记失败')
    }
  }

  const releaseMaintenance = async (tank: BoardTank) => {
    const record = board?.maintenance.find((m) => m.tank_no === tank.tank_no)
    if (!record) return
    const res = await removeTankMaintenance(record.id)
    if (res.code === 200) {
      message.success(`${tank.tank_no} 已解除检修`)
      await loadBoard()
    } else {
      message.error(res.message || '解除失败')
    }
  }

  const kpi = board?.kpis
  const dash = '--'

  // 发酵罐实时状态：三台发酵罐 + 最近已放罐的一批（凑齐 4 批）
  const renderTanks = useMemo(() => {
    const rows: BoardTank[] = [...(board?.tanks || [])]
    const last = board?.recent?.[0]
    if (last && !rows.some((t) => t.status === 'dumped')) {
      rows.push({
        tank_no: last.tank_no || '已放罐批次',
        status: 'dumped',
        batch_no: last.batch_no,
        inoculate_at: null,
        cultured_hours: null,
        cycle_hours: null,
        dump_at: last.dump_date,
        note: last.result,
      })
    }
    return rows
  }, [board])

  const kpiCards: {
    title: string
    value: string | number | null
    sub?: string
  }[] = [
    {
      title: '本月计划批次',
      value: kpi?.month_planned ?? dash,
      sub: board?.period.label,
    },
    { title: '本月满产目标批次', value: dash },
    { title: '计划达成率', value: dash },
    { title: '当前运行批次', value: kpi?.running ?? dash },
    { title: '待启动排产批次', value: kpi?.pending ?? dash },
    {
      title: '本月已完成批次',
      value: kpi?.month_done_planned ?? dash,
      sub: '按计划放罐口径',
    },
    { title: '染菌数｜染菌率', value: dash },
    { title: '计划月产能｜实际累计产能', value: dash },
    { title: '平均放罐收率', value: dash },
    { title: '设备利用率', value: dash },
    { title: '昨日单批平均产量', value: dash },
    { title: '本月批次合格率', value: dash },
  ]

  const tankColumns = [
    { title: '罐号', dataIndex: 'tank_no', key: 'tank_no', width: 90 },
    {
      title: '当前状态',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: string) => {
        const meta = STATUS_META[status] || { label: status, color: 'default' }
        return <Tag color={meta.color}>{meta.label}</Tag>
      },
    },
    {
      title: '当前批次号',
      dataIndex: 'batch_no',
      key: 'batch_no',
      width: 130,
      render: (v: string | null) => v || '-',
    },
    {
      title: '接种时间',
      dataIndex: 'inoculate_at',
      key: 'inoculate_at',
      width: 140,
      render: (v: string | null) => fmtShort(v),
    },
    {
      title: '已培养时长',
      dataIndex: 'cultured_hours',
      key: 'cultured_hours',
      width: 110,
      render: (v: number | null) => (v == null ? '-' : `${Math.max(0, Math.floor(v))}h`),
    },
    {
      title: '计划总周期',
      dataIndex: 'cycle_hours',
      key: 'cycle_hours',
      width: 110,
      render: (v: number | null) => (v == null ? '-' : `${v}h`),
    },
    {
      title: '预估放罐时间',
      dataIndex: 'dump_at',
      key: 'dump_at',
      width: 150,
      render: (v: string | null) => fmtShort(v),
    },
    {
      title: '备注',
      dataIndex: 'note',
      key: 'note',
      render: (v: string | null) => v || '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_: unknown, record: BoardTank) =>
        record.status === 'dumped' ? (
          '-'
        ) : record.status === 'maintenance' ? (
          <Button size="small" onClick={() => void releaseMaintenance(record)}>
            解除检修
          </Button>
        ) : (
          <Button
            size="small"
            icon={<ToolOutlined />}
            onClick={() => {
              setMaintTank(record)
              setMaintReason('')
              setMaintModalOpen(true)
            }}
          >
            标记检修
          </Button>
        ),
    },
  ]

  const recentColumns = [
    { title: '批次号', dataIndex: 'batch_no', key: 'batch_no' },
    {
      title: '放罐日期',
      dataIndex: 'dump_date',
      key: 'dump_date',
      width: 120,
    },
    {
      title: '放罐产量',
      dataIndex: 'yield_kg',
      key: 'yield_kg',
      width: 110,
      render: (v: number | null) => (v == null ? '--' : `${v} kg`),
    },
    {
      title: '实际收率',
      dataIndex: 'yield_rate',
      key: 'yield_rate',
      width: 100,
      render: (v: number | null) => (v == null ? '--' : `${v}%`),
    },
    { title: '结果', dataIndex: 'result', key: 'result', width: 110 },
  ]

  const trendOption = board?.trend
    ? {
        xAxis: { type: 'category', data: board.trend.batches },
        yAxis: { type: 'value', name: '收率 (%)' },
        series: [{ type: 'line', data: board.trend.yields, smooth: true }],
      }
    : null

  const hasWarn = (board?.alerts || []).some((a) => a.level === 'warn')
  const alertText = (board?.alerts || []).map((a) => a.text).join('　　｜　　')

  return (
    <div className="p-4 space-y-4">
      {/* 顶部通栏 */}
      <Card
        variant="borderless"
        className="shadow-sm"
        styles={{ body: { padding: '12px 20px' } }}
      >
        <div className="flex items-center justify-between flex-wrap gap-2">
          <Space size={12}>
            <ScheduleOutlined style={{ fontSize: 22, color: '#1677ff' }} />
            <Title level={4} style={{ margin: 0 }}>
              发酵车间生产实时看板
            </Title>
            {board?.period && <Tag color="blue">生产周期 {board.period.label}</Tag>}
          </Space>
          <Space size={16}>
            <Text type="secondary">系统时间：{clock}</Text>
            <Text type="secondary">数据刷新：5 分钟</Text>
            <Button
              size="small"
              icon={<SyncOutlined spin={loading} />}
              onClick={() => void loadBoard()}
            >
              立即刷新
            </Button>
          </Space>
        </div>
      </Card>

      {/* 告警跑马灯 */}
      <Card
        variant="borderless"
        className="shadow-sm"
        styles={{ body: { padding: '6px 20px', overflow: 'hidden' } }}
      >
        <div className="flex items-center gap-2">
          <AlertOutlined
            style={{ color: hasWarn ? '#fa8c16' : '#52c41a' }}
          />
          <div className="overflow-hidden flex-1">
            <div
              style={{
                display: 'inline-block',
                whiteSpace: 'nowrap',
                animation: 'board-marquee 24s linear infinite',
                color: hasWarn ? '#d46b08' : '#389e0d',
              }}
            >
              {alertText || '车间运行正常，无待处理播报'}
            </div>
          </div>
        </div>
      </Card>
      <style>{`
        @keyframes board-marquee {
          0% { transform: translateX(100%); }
          100% { transform: translateX(-100%); }
        }
      `}</style>

      {/* 主体 */}
      {loading && !board ? (
        <Card variant="borderless" className="shadow-sm">
          <Empty description="看板加载中…" />
        </Card>
      ) : boardMessage && !board ? (
        <Card variant="borderless" className="shadow-sm">
          <Empty description={boardMessage} />
        </Card>
      ) : (
        <>
          {/* KPI 卡片区 */}
          <Row gutter={[12, 12]}>
            {kpiCards.map((card) => (
              <Col xs={12} sm={8} md={6} lg={4} key={card.title}>
                <Card
                  variant="borderless"
                  className="shadow-sm"
                  styles={{ body: { padding: '10px 14px' } }}
                >
                  <Statistic
                    title={<span style={{ fontSize: 12 }}>{card.title}</span>}
                    value={card.value ?? undefined}
                    styles={{ content: { fontSize: 26, fontWeight: 600 } }}
                  />
                  {card.sub && (
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {card.sub}
                    </Text>
                  )}
                </Card>
              </Col>
            ))}
          </Row>

          {/* 三台罐状态 */}
          <Card
            title="发酵罐实时状态"
            variant="borderless"
            className="shadow-sm"
            styles={{ body: { padding: 8 } }}
          >
            <Table
              rowKey={(t: BoardTank) =>
                t.status === 'dumped' ? `dumped-${t.batch_no}` : t.tank_no
              }
              size="small"
              columns={tankColumns}
              dataSource={renderTanks}
              pagination={false}
            />
          </Card>

          {/* 收率趋势 + 最近完成批次 */}
          <Row gutter={[12, 12]}>
            <Col xs={24} lg={12}>
              <Card
                title="近 12 批收率走势"
                variant="borderless"
                className="shadow-sm"
                styles={{ body: { padding: 8 } }}
              >
                {trendOption ? (
                  <ReactECharts option={trendOption} style={{ height: 260 }} />
                ) : (
                  <Empty
                    description="实际放罐数据接入后显示（当前为计划看板）"
                    style={{ padding: '70px 0' }}
                  />
                )}
              </Card>
            </Col>
            <Col xs={24} lg={12}>
              <Card
                title="最近完成批次"
                variant="borderless"
                className="shadow-sm"
                styles={{ body: { padding: 8 } }}
              >
                <Table
                  rowKey="batch_no"
                  size="small"
                  columns={recentColumns}
                  dataSource={board?.recent || []}
                  pagination={false}
                  locale={{ emptyText: '暂无已到计划放罐时间的批次' }}
                />
              </Card>
            </Col>
          </Row>
        </>
      )}

      {/* 检修标注弹窗 */}
      <Modal
        title={`标记检修：${maintTank?.tank_no || ''}`}
        open={maintModalOpen}
        onOk={() => void submitMaintenance()}
        onCancel={() => setMaintModalOpen(false)}
        okText="确认标记"
        cancelText="取消"
      >
        <Input
          placeholder="检修原因（如：滤芯更换）"
          value={maintReason}
          onChange={(e) => setMaintReason(e.target.value)}
        />
        <Text type="secondary" style={{ fontSize: 12 }}>
          标记后该罐在看板上显示「检修维护」，可随时解除。
        </Text>
      </Modal>

      {/* 底部：生产车间入口 */}
      <Card title="生产车间" variant="borderless" className="shadow-sm">
        <Row gutter={[16, 16]}>
          {workshopItems.map((item) => (
            <Col span={8} key={item.key}>
              <div
                data-testid={`workshop-entry:${item.key}`}
                className="p-4 rounded-lg border border-[var(--color-hairline)] hover:border-[var(--color-primary)] cursor-pointer transition-colors"
                onClick={() => router.push(item.key)}
              >
                <Space align="start">
                  <div
                    className="w-10 h-10 rounded-lg flex items-center justify-center text-white text-lg"
                    style={{ backgroundColor: item.color }}
                  >
                    <ShopOutlined />
                  </div>
                  <div>
                    <Text strong className="block">
                      {item.title}
                    </Text>
                    <Text type="secondary" className="text-xs">
                      {item.description}
                    </Text>
                  </div>
                  <ArrowRightOutlined className="text-[var(--color-muted)] ml-auto" />
                </Space>
              </div>
            </Col>
          ))}
        </Row>
      </Card>
    </div>
  )
}
