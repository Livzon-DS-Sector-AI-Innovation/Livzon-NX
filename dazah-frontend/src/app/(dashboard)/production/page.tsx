'use client'

// 发酵车间生产实时看板（生产管理概览页，一期：计划驱动）
// 数据源：最新排产 Excel 存档（当前扎帐周期块）+ 人工检修标注。
// 实际完成/收率/合格率等指标待实际数据接入后启用（当前显示 --）。

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
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
  InputNumber,
  DatePicker,
  Drawer,
  Popconfirm,
  Select,
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
  DatabaseOutlined,
  PlusOutlined,
  EditOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import ReactECharts from 'echarts-for-react'
import BoardNavBlocks from '@/components/production/board-nav-blocks'
import ProgressParticles from '@/components/production/progress-particles'
import { useProductContextStore } from '@/stores/product-context'
import { usePermission } from '@/hooks/usePermission'
import {
  getFermentationBoard,
  markTankMaintenance,
  removeTankMaintenance,
  getFermentationBatchActuals,
  upsertFermentationBatchActual,
  deleteFermentationBatchActual,
  setFermentationMonthCapacity,
  getPlans,
} from '@/actions/production'
import type {
  FermentationBoard,
  BoardTank,
  FermentationBatchActual,
  FermentationBatchActualFormData,
  ProductionPlan,
} from '@/types/production'

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

// 提炼计划产量卡的下拉选择记忆（按月份存 {月份: "车间|产品"}），刷新后恢复
const PLAN_SELECTION_STORAGE_KEY = 'dazah.production.plan-card.selection'

// 当前产品（第 5 个导航位）：看板标题与产品入口共用
const PRODUCT_NAME = 'L-苯丙氨酸'

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

// 批次顺序号 = 批次号后三位（如 FA26234 → 234）；无法解析时返回 null，排序时置于末尾
function batchSeqNo(batchNo: string | null): number | null {
  if (!batchNo) return null
  const tail = batchNo.slice(-3)
  return /^\d{3}$/.test(tail) ? Number(tail) : null
}

const STATUS_META: Record<string, { label: string; color: string }> = {
  running: { label: '运行中', color: 'success' },
  dumping: { label: '放罐中', color: 'processing' },
  idle: { label: '检修待投料', color: 'default' },
  maintenance: { label: '检修维护', color: 'warning' },
  dumped: { label: '已放罐', color: 'default' },
}

export default function ProductionDashboard() {
  const router = useRouter()
  const { message } = App.useApp()
  // 工段数据权限：发酵模块挂发酵权限，提炼汇总挂提炼权限，收率需双权限
  const { has } = usePermission()
  const canFerm = has('production:fermentation-yield')
  const canExtract = has('production:extraction-yield')
  const [board, setBoard] = useState<FermentationBoard | null>(null)
  const [boardMessage, setBoardMessage] = useState<string>('')
  const [loading, setLoading] = useState(true)
  // 周期回看：空串 = 今天所在周期；否则为所选周期内任意日期
  const [viewDate, setViewDate] = useState<string>('')
  // 当前产品上下文（导航块第 5 位切换），看板按此产品取数
  const productCode = useProductContextStore((s) => s.productCode)
  // 首帧不渲染时间（服务端与客户端时区不一致会导致 hydration 不匹配），挂载后再计时
  const [clock, setClock] = useState('')
  const [maintModalOpen, setMaintModalOpen] = useState(false)
  const [maintTank, setMaintTank] = useState<BoardTank | null>(null)
  const [maintReason, setMaintReason] = useState('')
  const [actualsOpen, setActualsOpen] = useState(false)
  const [actuals, setActuals] = useState<FermentationBatchActual[]>([])
  const [actualsLoading, setActualsLoading] = useState(false)
  const [actualModalOpen, setActualModalOpen] = useState(false)
  const [editingActual, setEditingActual] = useState<FermentationBatchActual | null>(null)
  const [actualBatchNo, setActualBatchNo] = useState('')
  const [actualDumpDate, setActualDumpDate] = useState<dayjs.Dayjs | null>(null)
  const [actualYieldKg, setActualYieldKg] = useState<number | null>(null)
  const [actualRemark, setActualRemark] = useState('')
  const [capacityModalOpen, setCapacityModalOpen] = useState(false)
  const [capacityKg, setCapacityKg] = useState<number | null>(null)
  // 提炼计划产量卡：生产计划（飞书同步）按概览自然月取数，下拉选"车间 产品"行
  const [planRows, setPlanRows] = useState<ProductionPlan[]>([])
  const [selectedPlanKey, setSelectedPlanKey] = useState('')
  const planMonth = viewDate
    ? dayjs(viewDate).format('YYYY-MM')
    : dayjs().format('YYYY-MM')
  const planKey = (row: ProductionPlan) =>
    `${row.workshop ?? ''}|${row.product_name}`

  const loadBoard = useCallback(async () => {
    try {
      const res = await getFermentationBoard(
        viewDate || undefined,
        productCode,
      )
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
  }, [viewDate, productCode])

  useEffect(() => {
    void loadBoard() // eslint-disable-line react-hooks/set-state-in-effect -- 看板初始加载，与 201-2 页面既有模式一致
    const timer = setInterval(() => void loadBoard(), REFRESH_INTERVAL_MS)
    return () => clearInterval(timer)
  }, [loadBoard])

  // 提炼计划产量：跟随概览自然月拉生产计划；选择按月记入本地存储，
  // 页面刷新后恢复所选行，仅当该行不在当月数据时才回退第一行
  useEffect(() => {
    let cancelled = false
    void (async () => {
      let remembered = ''
      try {
        const store = JSON.parse(
          window.localStorage.getItem(PLAN_SELECTION_STORAGE_KEY) || '{}',
        )
        remembered = typeof store[planMonth] === 'string' ? store[planMonth] : ''
      } catch {
        // 存储不可用则当作无记录
      }
      try {
        const res = await getPlans({ month: planMonth, page_size: 200 })
        if (res.code === 200 && !cancelled) {
          const rows = res.data || []
          setPlanRows(rows)
          setSelectedPlanKey((prev) => {
            if (rows.length === 0) return ''
            for (const key of [prev, remembered]) {
              if (key && rows.some((r) => planKey(r) === key)) return key
            }
            return planKey(rows[0])
          })
        }
      } catch {
        if (!cancelled) setPlanRows([])
      }
    })()
    return () => {
      cancelled = true
    }
  }, [planMonth])

  // 显式选择时写入本地存储（按月份分开记忆）
  const handlePlanSelect = useCallback(
    (key: string) => {
      setSelectedPlanKey(key)
      try {
        const raw = window.localStorage.getItem(PLAN_SELECTION_STORAGE_KEY)
        const store = raw ? JSON.parse(raw) : {}
        store[planMonth] = key
        window.localStorage.setItem(
          PLAN_SELECTION_STORAGE_KEY,
          JSON.stringify(store),
        )
      } catch {
        // 存储不可用时仅当次会话生效
      }
    },
    [planMonth],
  )

  useEffect(() => {
    const update = () => setClock(fmtDateTime(new Date().toISOString()))
    // rAF 异步回调补首帧时间，避免 effect 内同步 setState
    const raf = requestAnimationFrame(update)
    const timer = setInterval(update, 1000)
    return () => {
      cancelAnimationFrame(raf)
      clearInterval(timer)
    }
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

  const openActuals = async () => {
    setActualsOpen(true)
    setActualsLoading(true)
    try {
      const res = await getFermentationBatchActuals(
        board?.period.start,
        board?.period.end,
      )
      if (res.code === 200) {
        setActuals(res.data || [])
      } else {
        message.error(res.message || '历史数据加载失败')
      }
    } catch {
      message.error('历史数据加载失败')
    } finally {
      setActualsLoading(false)
    }
  }

  const openActualModal = (item: FermentationBatchActual | null) => {
    setEditingActual(item)
    setActualBatchNo(item?.batch_no ?? '')
    setActualDumpDate(item?.dump_date ? dayjs(item.dump_date) : null)
    setActualYieldKg(item?.yield_kg ?? null)
    setActualRemark(item?.remark ?? '')
    setActualModalOpen(true)
  }

  const submitActual = async () => {
    if (!actualBatchNo.trim()) {
      message.warning('请填写批次号')
      return
    }
    // 仅提交当前账号有权限的字段：后端按显式字段更新，跨工段数据互不清除
    const payload: FermentationBatchActualFormData = {
      batch_no: actualBatchNo.trim(),
    }
    if (canFerm) {
      payload.dump_date = actualDumpDate
        ? actualDumpDate.format('YYYY-MM-DD')
        : null
      payload.yield_kg = actualYieldKg
      payload.remark = actualRemark.trim() || null
    }
    const res = await upsertFermentationBatchActual(payload)
    if (res.code === 200) {
      message.success('已保存批次产量')
      setActualModalOpen(false)
      await openActuals()
      await loadBoard()
    } else {
      message.error(res.message || '保存失败')
    }
  }

  const removeActual = async (item: FermentationBatchActual) => {
    const res = await deleteFermentationBatchActual(item.id)
    if (res.code === 200) {
      message.success('已删除批次产量记录')
      await openActuals()
      await loadBoard()
    } else {
      message.error(res.message || '删除失败')
    }
  }

  const openCapacityModal = () => {
    setCapacityKg(board?.month_planned_capacity_kg ?? null)
    setCapacityModalOpen(true)
  }

  const submitCapacity = async () => {
    const res = await setFermentationMonthCapacity(capacityKg)
    if (res.code === 200) {
      message.success('已保存本月计划产能')
      setCapacityModalOpen(false)
      await loadBoard()
    } else {
      message.error(res.message || '保存失败')
    }
  }

  const kpi = board?.kpis
  // 周期回看：写操作（检修、产能设置）仅当前扎帐月开放
  const isCurrent = board?.is_current_period ?? true
  const dash = '--'
  // 「提炼已出成品（仓储成品入库）」：当期仓储入库合计；仅接入产品有值
  const extractInboundKg = board?.extract_finished_inbound_kg ?? null
  // 「提炼计划产量」当前选中行（车间+产品）
  const selectedPlan =
    planRows.find((r) => planKey(r) === selectedPlanKey) ?? null
  // 完成率 = 已出成品 ÷ 当前选中行的计划产量，百分比保留两位小数
  const extractPlanRate =
    extractInboundKg != null && selectedPlan?.planned_yield
      ? `${((extractInboundKg / selectedPlan.planned_yield) * 100).toFixed(2)}%`
      : dash

  // 发酵罐实时状态：三台发酵罐 + 最近已放罐的一批（凑齐 4 批）
  // 行序按批次顺序（批次号后三位从小到大）；无批号的罐（空闲/检修）保持罐号顺序排在最后
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
        note: '该罐本批次放罐作业完成',
      })
    }
    rows.sort(
      (a, b) =>
        (batchSeqNo(a.batch_no) ?? Number.POSITIVE_INFINITY) -
        (batchSeqNo(b.batch_no) ?? Number.POSITIVE_INFINITY),
    )
    return rows
  }, [board])

  const achievementRate =
    kpi?.month_done_planned != null && kpi?.month_planned
      ? Math.round((kpi.month_done_planned / kpi.month_planned) * 100)
      : null

  // 产能口径公共变量：已完成产能、计划产能与格式化
  const doneYieldKg = kpi?.month_done_yield_kg ?? null
  const plannedCapacityKg = board?.month_planned_capacity_kg ?? null
  const capacityRate =
    doneYieldKg != null && plannedCapacityKg
      ? `${((doneYieldKg / plannedCapacityKg) * 100).toFixed(2)}%`
      : null
  // 产能口径统一按 kg 展示（千分位 + 单位）；已完成产能等实测口径保留两位小数
  const fmtKg = (kg: number | null, decimals = 0) =>
    kg == null
      ? '--'
      : `${kg.toLocaleString('zh-CN', {
          minimumFractionDigits: decimals,
          maximumFractionDigits: decimals,
        })} kg`
  // 历史数据/产量数值：两位小数
  const fmtNum2 = (v: number | null | undefined) =>
    v == null ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

  // 本月批次进度条：已完成（产量已录）→ 待出产量（已放罐未录产量）→ 运行中 → 未开始
  // 产能口径：已完成段宽度 = 已完成产能/计划产能，箭头随之；
  // 剩余宽度按待出产量/运行中/未开始的批次数比例分配（段内仍显示批数）
  const planned = kpi?.month_planned ?? 0
  const doneWithYield = kpi?.done_with_yield ?? 0
  const yieldPending = kpi?.yield_pending ?? 0
  const runningCount = kpi?.running ?? 0
  const notStarted = Math.max(0, planned - doneWithYield - yieldPending - runningCount)
  const segPct = (count: number) => (planned > 0 ? (count / planned) * 100 : 0)
  const capacityMode = plannedCapacityKg != null && plannedCapacityKg > 0
  // 产能达成率 ≥ 100% 时进度条粒子进入最高密度模式（Ultra）
  const capacityUltra =
    capacityMode && doneYieldKg != null && plannedCapacityKg != null
      ? doneYieldKg >= plannedCapacityKg
      : false
  const greenPct =
    capacityMode && doneYieldKg != null
      ? Math.min(100, (doneYieldKg / plannedCapacityKg) * 100)
      : segPct(doneWithYield)
  const arrowPct = greenPct
  const restBatches = yieldPending + runningCount + notStarted
  const restPct = 100 - greenPct
  const restSegPct = (count: number) =>
    restBatches > 0 ? (count / restBatches) * restPct : 0
  const greenLabel =
    capacityMode && doneYieldKg != null
      ? `已完成 ${doneWithYield} 批｜${fmtKg(doneYieldKg, 2)}`
      : `${doneWithYield}`

  const progressSegments = [
    { key: 'done', label: '已完成', count: doneWithYield, color: '#33526e' },
    { key: 'pending', label: '待出产量', count: yieldPending, color: '#94a3b8' },
    { key: 'running', label: '运行中', count: runningCount, color: '#7ea6c9' },
    { key: 'idle', label: '未开始', count: notStarted, color: '#e8eef4' },
  ]
  // 箭头两个斜角用右侧第一个有数据的段颜色填充
  const nextSegment = progressSegments.find(
    (seg) => seg.key !== 'done' && seg.count > 0,
  )
  const arrowNotchColor = nextSegment?.color ?? '#f0f0f0'

  // 理论批次：一天一批，当前周期截至今天、历史周期截至周期末
  const asOfDay = isCurrent ? dayjs() : dayjs(board?.period.end ?? undefined)
  const asOfLabel = asOfDay.isValid() ? asOfDay.format('MM-DD') : '--'
  const theoryBatches =
    board?.period.start && board?.period.end
      ? Math.max(
          0,
          Math.min(
            asOfDay.diff(dayjs(board.period.start), 'day') + 1,
            dayjs(board.period.end).diff(dayjs(board.period.start), 'day') + 1,
          ),
        )
      : null
  const utilizationRate =
    theoryBatches && kpi?.month_done_planned != null
      ? Math.round((kpi.month_done_planned / theoryBatches) * 100)
      : null

  const kpiCards: {
    title: string
    value: string | number | null
    sub?: string
    span?: number
    extra?: { label: string; value: string; sub?: string; editable?: boolean }
  }[] = [
    {
      title: '发酵本月计划批次',
      value: kpi?.month_planned ?? dash,
      sub: board?.period.label,
      span: 8,
      extra: {
        label: '发酵本月计划产能',
        value: fmtKg(plannedCapacityKg),
        sub: '按扎帐月保存，可修改',
        editable: true,
      },
    },
    {
      title: '发酵本月已完成批次',
      value: kpi?.month_done_planned ?? dash,
      sub: achievementRate != null ? `达成率 ${achievementRate}%` : undefined,
      span: 8,
      extra: {
        label: '发酵已完成产能',
        value: fmtKg(doneYieldKg, 2),
        sub: `产能达成率 ${capacityRate ?? '--'}`,
      },
    },
    {
      title: '发酵理论批次',
      value: theoryBatches != null ? theoryBatches : dash,
      sub: `截至 ${asOfLabel} · 一天一批`,
      span: 8,
      extra: {
        label: '发酵设备利用率',
        value: utilizationRate != null ? `${utilizationRate}%` : dash,
        sub: `已完成 ${kpi?.month_done_planned ?? dash} ÷ 理论 ${theoryBatches ?? dash}`,
      },
    },
  ]

  const tankColumns = [
    { title: '罐号', dataIndex: 'tank_no', key: 'tank_no', width: 80 },
    {
      title: '当前状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => {
        const meta = STATUS_META[status] || { label: status, color: 'default' }
        return <Tag color={meta.color}>{meta.label}</Tag>
      },
    },
    {
      title: '当前批次号',
      dataIndex: 'batch_no',
      key: 'batch_no',
      width: 110,
      render: (v: string | null) => v || '-',
    },
    {
      title: '移种时间',
      dataIndex: 'inoculate_at',
      key: 'inoculate_at',
      width: 124,
      render: (v: string | null) => fmtShort(v),
    },
    {
      title: '已培养时长',
      dataIndex: 'cultured_hours',
      key: 'cultured_hours',
      width: 88,
      render: (v: number | null) => (v == null ? '-' : `${Math.max(0, Math.floor(v))}h`),
    },
    {
      title: '计划总周期',
      dataIndex: 'cycle_hours',
      key: 'cycle_hours',
      width: 88,
      render: (v: number | null) => (v == null ? '-' : `${v}h`),
    },
    {
      title: '预估放罐时间',
      dataIndex: 'dump_at',
      key: 'dump_at',
      width: 136,
      render: (v: string | null) => fmtShort(v),
    },
    {
      title: '备注',
      dataIndex: 'note',
      key: 'note',
      ellipsis: { showTitle: true },
      render: (v: string | null) => v || '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_: unknown, record: BoardTank) =>
        record.status === 'dumped' || !isCurrent ? (
          // 占位与操作列 small 按钮同高（主题 controlHeightSM），保证已放罐行与其他行行高一致；
          // 历史周期为只读视图，不提供检修操作
          <span style={{ display: 'inline-block', height: 36, lineHeight: '36px' }}>-</span>
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
    {
      title: '罐号',
      dataIndex: 'tank_no',
      key: 'tank_no',
      width: 64,
      render: (v: string | null | undefined) => v || '-',
    },
    { title: '批次号', dataIndex: 'batch_no', key: 'batch_no' },
    {
      title: '放罐日期',
      dataIndex: 'dump_date',
      key: 'dump_date',
      width: 76,
      render: (v: string | null) => fmtShort(v),
    },
    {
      title: '放罐产量(kg)',
      dataIndex: 'yield_kg',
      key: 'yield_kg',
      width: 96,
      render: (v: number | null) => fmtNum2(v),
    },
    {
      title: '备注',
      dataIndex: 'remark',
      key: 'remark',
      ellipsis: { showTitle: true },
      render: (v: string | null) => v || '-',
    },
  ]

  // 新建录入时的批号下拉：已放罐且尚未录入产量的批次；编辑时锁定原批号
  const actualBatchOptions = editingActual
    ? [{ label: editingActual.batch_no, value: editingActual.batch_no }]
    : (board?.dumped_batches || [])
        .filter((b) => !actuals.some((a) => a.batch_no === b.batch_no))
        .map((b) => ({ label: `${b.batch_no}（${b.dump_date}）`, value: b.batch_no }))

  const actualColumns = [
    {
      title: '罐号',
      dataIndex: 'tank_no',
      key: 'tank_no',
      width: 64,
      render: (v: string | null | undefined) => v || '-',
    },
    { title: '批次号', dataIndex: 'batch_no', key: 'batch_no' },
    {
      title: '放罐日期',
      dataIndex: 'dump_date',
      key: 'dump_date',
      width: 110,
      render: (v: string | null) => v || '-',
    },
    ...(canFerm
      ? [
          {
            title: '产量(kg)',
            dataIndex: 'yield_kg',
            key: 'yield_kg',
            width: 100,
            render: (v: number | null) => fmtNum2(v),
          },
        ]
      : []),
    {
      title: '备注',
      dataIndex: 'remark',
      key: 'remark',
      ellipsis: { showTitle: true },
      render: (v: string | null) => v || '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 110,
      render: (_: unknown, record: FermentationBatchActual) => (
        <Space size={0}>
          <Button size="small" type="link" onClick={() => openActualModal(record)}>
            编辑
          </Button>
          <Popconfirm
            title="删除后看板图表不再统计该批次，确认删除？"
            okText="删除"
            cancelText="取消"
            onConfirm={() => void removeActual(record)}
          >
            <Button size="small" type="link" danger>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  // 单批产量柱状图 + 平均产量标线
  const trendOutputs = board?.trend?.outputs ?? []
  const trendAvg = trendOutputs.length
    ? trendOutputs.reduce((sum, value) => sum + value, 0) / trendOutputs.length
    : null

  const trendOption = board?.trend
    ? {
        // containLabel 让绘图区给 Y 轴标签让位，避免第一根柱被轴刻度遮挡
        grid: { left: 8, right: 24, top: 40, bottom: 40, containLabel: true },
        xAxis: {
          type: 'category',
          data: board.trend.batches,
          axisLabel: { interval: 'auto', hideOverlap: true },
        },
        yAxis: { type: 'value', name: '产量 (kg)' },
        dataZoom: [
          {
            type: 'slider',
            xAxisIndex: 0,
            start: 0,
            end: 100,
            height: 16,
            bottom: 8,
          },
        ],
        tooltip: { trigger: 'axis' },
        series: [
          {
            type: 'bar',
            name: '单批产量',
            data: trendOutputs,
            barMaxWidth: 36,
            markLine:
              trendAvg == null
                ? undefined
                : {
                    symbol: 'none',
                    silent: true,
                    lineStyle: { color: '#fa8c16' },
                    label: {
                      formatter: `平均产量 ${trendAvg.toFixed(1)} kg`,
                      position: 'insideEndTop',
                    },
                    data: [{ yAxis: trendAvg }],
                  },
          },
        ],
      }
    : null

  const hasWarn = (board?.alerts || []).some((a) => a.level === 'warn')
  const alertText = (board?.alerts || []).map((a) => a.text).join('　　｜　　')

  return (
    <div className="p-4 flex flex-col gap-3">
      {/* 顶部导航块：第 5 位为当前产品 L-苯丙氨酸，其余为占位 */}
      <BoardNavBlocks />

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
              {`103-1车间${PRODUCT_NAME}生产看板`}
            </Title>
            <DatePicker
              size="small"
              picker="month"
              allowClear={false}
              style={{ width: 96 }}
              value={
                viewDate
                  ? dayjs(viewDate)
                  : board?.period.end
                    ? dayjs(board.period.end)
                    : null
              }
              onChange={(d) => {
                // 选自然月 → 定位到主要落在该月的扎帐周期（该月 15 日必在其中）
                if (d) setViewDate(d.date(15).format('YYYY-MM-DD'))
              }}
            />
            {board?.period && <Tag color="blue">生产周期 {board.period.label}</Tag>}
            {!isCurrent && (
              <Button size="small" onClick={() => setViewDate('')}>
                回到本月
              </Button>
            )}
          </Space>
          <Space size={16}>
            <Text type="secondary">系统时间：{clock}</Text>
            <Text type="secondary">数据刷新：5 分钟</Text>
            <Button
              size="small"
              icon={<DatabaseOutlined />}
              onClick={() => void openActuals()}
            >
              历史数据
            </Button>
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
        /* 计划卡的产品下拉：压缩到 24px，标题行不高于普通卡片标题 */
        .plan-product-select.ant-select-single {
          height: 24px;
        }
        .plan-product-select .ant-select-selector {
          height: 24px !important;
          min-height: 24px !important;
          padding: 0 6px;
        }
        .plan-product-select .ant-select-selection-item {
          line-height: 22px;
        }
        /* 最近完成批次：表格区域撑满卡片高度，滚动条贴卡片右缘上下撑满 */
        .recent-batches-card {
          display: flex;
          flex-direction: column;
        }
        .recent-batches-card .ant-card-body {
          flex: 1;
          min-height: 0;
          display: flex;
          flex-direction: column;
        }
        .recent-batches-table,
        .recent-batches-table .ant-spin,
        .recent-batches-table .ant-spin-container,
        .recent-batches-table .ant-table,
        .recent-batches-table .ant-table-container {
          flex: 1;
          min-height: 0;
          display: flex;
          flex-direction: column;
        }
        .recent-batches-table .ant-table-body {
          flex: 1;
          min-height: 0;
          overflow-y: auto;
        }
        /* 收率分析预留位：撑满卡片，虚线框占位 */
        .extraction-rate-placeholder {
          height: 100%;
          min-height: 72px;
          display: flex;
          align-items: center;
          justify-content: center;
          border: 1px dashed var(--color-hairline);
          border-radius: 8px;
        }
        /* 提炼工段卡片行：与上方 KPI 行保持同一高度 */
        .extraction-summary-row > .ant-col {
          height: 108px;
        }
        .extraction-summary-row .ant-card {
          height: 100%;
          overflow: hidden;
        }
        .extraction-summary-row .extraction-rate-placeholder {
          min-height: 0;
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
          {canFerm && (
            <>
          {/* KPI 卡片区 */}
          <Row gutter={[12, 12]}>
            {kpiCards.map((card) => (
              <Col
                xs={12}
                sm={12}
                md={card.span ?? 6}
                key={card.title}
              >
                <Card
                  variant="borderless"
                  className="shadow-sm h-full"
                  styles={{ body: { padding: '10px 14px' } }}
                >
                  <div className={card.extra ? 'flex items-stretch' : undefined}>
                    <div className={card.extra ? 'flex-1 min-w-0' : undefined}>
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
                    </div>
                    {card.extra && (
                      <div className="flex-1 min-w-0 pl-3 border-l border-[var(--color-hairline)]">
                        <Text
                          type="secondary"
                          style={{ fontSize: 12, display: 'block', marginBottom: 7 }}
                        >
                          {card.extra.label}
                        </Text>
                        <div
                          className="flex items-center gap-1"
                          style={{ marginBottom: 4, minHeight: 35 }}
                        >
                          <div style={{ fontSize: 26, fontWeight: 600, lineHeight: 1.35 }}>
                            {card.extra.value}
                          </div>
                          {card.extra.editable && isCurrent && (
                            <Button
                              type="text"
                              size="small"
                              icon={<EditOutlined />}
                              onClick={openCapacityModal}
                              title="设置本月计划产能"
                            />
                          )}
                        </div>
                        {card.extra.sub && (
                          <Text type="secondary" style={{ fontSize: 11 }}>
                            {card.extra.sub}
                          </Text>
                        )}
                      </div>
                    )}
                  </div>
                </Card>
              </Col>
            ))}
          </Row>
            </>
          )}

          {/* 提炼工段卡片行：各卡按工段权限渲染（发酵产量=发酵岗，提炼成品=提炼岗，收率=双权限） */}
          {(canFerm || canExtract) && (
            <Row gutter={[12, 12]} className="extraction-summary-row">
              {canFerm && (
                <Col xs={24} md={8}>
                  <Card
                    variant="borderless"
                    className="shadow-sm h-full"
                    styles={{ body: { padding: '10px 14px' } }}
                  >
                    {/* 标题行 25px 顶部对齐（21px 文字 + 4px 间距），与 KPI 卡 Statistic 标题同构 */}
                    <div
                      className="flex items-start justify-between gap-2"
                      style={{ height: 25 }}
                    >
                      <span
                        style={{ fontSize: 12, lineHeight: '21px', marginTop: 2 }}
                      >
                        提炼计划产量
                      </span>
                      <Select
                        size="small"
                        variant="borderless"
                        className="plan-product-select"
                        value={selectedPlanKey || undefined}
                        onChange={handlePlanSelect}
                        placeholder="车间 · 产品"
                        style={{ width: 168, fontSize: 12 }}
                        options={planRows.map((r) => ({
                          value: planKey(r),
                          label: `${r.workshop ?? ''} ${r.product_name}`,
                        }))}
                        disabled={planRows.length === 0}
                      />
                    </div>
                    <Statistic
                      value={
                        selectedPlan?.planned_yield != null
                          ? selectedPlan.planned_yield.toLocaleString('zh-CN')
                          : dash
                      }
                      styles={{ content: { fontSize: 26, fontWeight: 600 } }}
                    />
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {planRows.length === 0
                        ? `${Number(planMonth.slice(5))}月生产计划待更新`
                        : selectedPlan?.planned_yield != null
                          ? `${selectedPlan.unit ?? ''} · ${Number(planMonth.slice(5))}月计划`
                          : '该行未填计划产量'}
                    </Text>
                  </Card>
                </Col>
              )}
              {canExtract && (
                <Col xs={24} md={8}>
                  <Card
                    variant="borderless"
                    className="shadow-sm h-full"
                    styles={{ body: { padding: '10px 14px' } }}
                  >
                    {/* 双栏结构（与 KPI 卡同构）：左=已出成品，右=完成率 */}
                    <div className="flex items-stretch">
                      <div className="flex-1 min-w-0">
                        <Statistic
                          title={
                            <span style={{ fontSize: 12 }}>
                              提炼已出成品（仓储成品入库）
                            </span>
                          }
                          value={extractInboundKg != null ? extractInboundKg : dash}
                          precision={extractInboundKg != null ? 0 : undefined}
                          styles={{ content: { fontSize: 26, fontWeight: 600 } }}
                        />
                        <Text type="secondary" style={{ fontSize: 11 }}>
                          {extractInboundKg != null
                            ? 'L-苯丙氨酸 · 本月合计(kg)'
                            : '数据源待接入'}
                        </Text>
                      </div>
                      <div className="flex-1 min-w-0 pl-3 border-l border-[var(--color-hairline)]">
                        <Text
                          type="secondary"
                          style={{
                            fontSize: 12,
                            display: 'block',
                            marginBottom: 7,
                          }}
                        >
                          完成率
                        </Text>
                        <div
                          className="flex items-center gap-1"
                          style={{ marginBottom: 4, minHeight: 35 }}
                        >
                          <div
                            style={{
                              fontSize: 26,
                              fontWeight: 600,
                              lineHeight: 1.35,
                            }}
                          >
                            {extractPlanRate}
                          </div>
                        </div>
                        <Text type="secondary" style={{ fontSize: 11 }}>
                          已出成品 ÷ 计划产量
                        </Text>
                      </div>
                    </div>
                  </Card>
                </Col>
              )}
              {(canFerm || canExtract) && (
                <Col xs={24} md={8}>
                  <Card
                    variant="borderless"
                    className="shadow-sm h-full"
                    styles={{ body: { padding: '10px 14px' } }}
                  >
                    {/* 收率分析预留位：内容待后续接入 */}
                    <div className="extraction-rate-placeholder">
                      <Empty
                        description="收率分析（待接入）"
                        image={Empty.PRESENTED_IMAGE_SIMPLE}
                      />
                    </div>
                  </Card>
                </Col>
              )}
            </Row>
          )}

          {canFerm && (
            <>
          {/* 本月批次进度条 */}
          <Card
            variant="borderless"
            className="shadow-sm"
            styles={{ body: { padding: '12px 20px' } }}
          >
            <div className="flex items-center justify-between flex-wrap gap-1">
              <div className="flex items-center gap-2 flex-wrap">
                <Text strong>{isCurrent ? '本月批次进度' : '历史批次进度'}</Text>
                {!isCurrent && <Tag color="orange">历史周期</Tag>}
              </div>
              {!capacityMode && isCurrent && (
                <Text type="secondary" style={{ fontSize: 12 }}>
                  未设置计划产能，进度暂按批次数展示；请编辑「本月计划产能」后切换产能口径
                </Text>
              )}
            </div>
            {/* 箭头骑在轨道上，指向已放罐进度点 */}
            <div className="relative" style={{ marginTop: 8, marginBottom: 4 }}>
              <div
                className="flex h-6 rounded overflow-hidden"
                style={{ position: 'relative', zIndex: 1 }}
              >
                {progressSegments.map((seg) => (
                  <div
                    key={seg.key}
                    title={
                      seg.key === 'done'
                        ? `${greenLabel}${
                            capacityMode && plannedCapacityKg
                              ? `（产能达成率 ${((greenPct)).toFixed(1)}%）`
                              : ''
                          }`
                        : `${seg.label} ${seg.count} 批`
                    }
                    className="h-full flex items-center justify-center overflow-hidden"
                    style={{
                      // 待出产量段向左多垫 34px：垫满箭头基部下方，与右侧连成一体无接缝
                      width:
                        seg.key === 'pending' && yieldPending > 0
                          ? `calc(${restSegPct(seg.count)}% + 34px)`
                          : `${seg.key === 'done' ? greenPct : restSegPct(seg.count)}%`,
                      backgroundColor: seg.color,
                      ...(seg.key === 'done'
                        ? { backgroundImage: 'linear-gradient(90deg, #33526e, #4a6d8c)' }
                        : {}),
                    }}
                  >
                    {seg.key === 'done' ? (
                      greenPct >= 14 && doneWithYield > 0 ? (
                        <span style={{ fontSize: 11, color: '#fff' }}>{greenLabel}</span>
                      ) : null
                    ) : (
                      seg.count > 0 &&
                      restSegPct(seg.count) >= 6 && (
                        <span
                          style={{
                            fontSize: 11,
                            color:
                              seg.key === 'idle' || seg.key === 'pending'
                                ? '#595959'
                                : '#fff',
                          }}
                        >
                          {seg.count}
                        </span>
                      )
                    )}
                  </div>
                ))}
              </div>
              {/* 粒子脉冲层：深蓝已完成段内的思考粒子（Codex 滑块同款动效） */}
              <ProgressParticles progressPct={arrowPct} ultra={capacityUltra} />
              {/* 箭头：轨道本身是横杠，大三角头（轨道2倍高）跨骑轨道、方向向右，
                  尖落在分界点；上下两个斜角填右侧段颜色 */}
              <div
                className="absolute"
                style={{
                  left: `${arrowPct}%`,
                  top: -12,
                  height: 48,
                  transform: 'translateX(-100%)',
                  zIndex: 3,
                }}
              >
                <svg width={34} height={48} viewBox="0 0 34 48" style={{ display: 'block' }}>
                  {/* 右侧色角块仅占据轨道高度带（沿对角线裁剪到 y=12~36） */}
                  <polygon points="17,12 34,12 34,24" fill={arrowNotchColor} />
                  <polygon points="17,36 34,36 34,24" fill={arrowNotchColor} />
                  {/* 箭身取轨道渐变末端色 #4a6d8c，与轨道右端无缝衔接 */}
                  <polygon points="0,0 34,24 0,48" fill="#4a6d8c" />
                </svg>
              </div>
            </div>
            <div className="flex items-center gap-4 flex-wrap">
              {progressSegments.map((seg) => (
                <span key={seg.key} className="flex items-center gap-1">
                  <span
                    className="inline-block w-2.5 h-2.5 rounded-sm"
                    style={{ backgroundColor: seg.color }}
                  />
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {seg.key === 'done'
                      ? `已完成 ${doneWithYield} 批${
                          capacityMode && doneYieldKg != null ? `｜${fmtKg(doneYieldKg, 2)}` : ''
                        }`
                      : `${seg.label} ${seg.count} 批`}
                  </Text>
                </span>
              ))}
            </div>
          </Card>

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
            </>
          )}

          {canFerm && (
            <>
          {/* 单批产量图表 + 最近完成批次：图表占 2/3，最近批次缩为 1/3 */}
          <Row gutter={[12, 12]}>
            <Col xs={24} lg={16}>
              <Card
                title="单批产量（最多 31 批）"
                variant="borderless"
                className="shadow-sm h-full"
                styles={{ body: { padding: 8 } }}
              >
                {trendOption ? (
                  <ReactECharts option={trendOption} style={{ height: 270 }} />
                ) : (
                  <Empty
                    description="暂无录入数据，请点击右上角「历史数据」录入批次产量"
                    style={{ padding: '70px 0' }}
                  />
                )}
              </Card>
            </Col>
            <Col xs={24} lg={8}>
              <Card
                title="最近完成批次"
                variant="borderless"
                className="shadow-sm h-full recent-batches-card"
                styles={{ body: { padding: 8 } }}
              >
                <Table
                  rowKey="batch_no"
                  size="small"
                  className="recent-batches-table"
                  columns={recentColumns}
                  dataSource={board?.recent || []}
                  pagination={false}
                  scroll={{ y: 243 }}
                  locale={{ emptyText: '暂无已完成放罐的批次' }}
                />
              </Card>
            </Col>
          </Row>
            </>
          )}
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

      {/* 历史数据抽屉：批次实际产量 */}
      <Drawer
        title="批次产量历史数据"
        size={560}
        open={actualsOpen}
        onClose={() => setActualsOpen(false)}
        extra={
          <Button
            type="primary"
            size="small"
            icon={<PlusOutlined />}
            onClick={() => openActualModal(null)}
          >
            录入批次产量
          </Button>
        }
      >
        <Table
          rowKey="id"
          size="small"
          columns={actualColumns}
          dataSource={actuals}
          loading={actualsLoading}
          pagination={false}
          locale={{ emptyText: '暂无录入数据' }}
        />
        <Text type="secondary" style={{ fontSize: 12 }}>
          录入后单批产量图表与「最近完成批次」的放罐产量自动更新。
        </Text>
      </Drawer>

      {/* 批次产量录入弹窗 */}
      <Modal
        title={editingActual ? `编辑批次产量：${editingActual.batch_no}` : '录入批次产量'}
        open={actualModalOpen}
        onOk={() => void submitActual()}
        onCancel={() => setActualModalOpen(false)}
        okText="保存"
        cancelText="取消"
      >
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          <Select
            showSearch
            placeholder="选择已放罐批次"
            style={{ width: '100%' }}
            value={actualBatchNo || undefined}
            disabled={Boolean(editingActual)}
            options={actualBatchOptions}
            notFoundContent="暂无已放罐批次"
            onChange={(value) => {
              setActualBatchNo(value)
              // 选中批次后自动带出排产的计划放罐日期，仍可手动修改
              const found = board?.dumped_batches.find((b) => b.batch_no === value)
              if (found?.dump_date) setActualDumpDate(dayjs(found.dump_date))
            }}
          />
          {canFerm && (
            <>
              <DatePicker
                placeholder="放罐日期（可选）"
                style={{ width: '100%' }}
                value={actualDumpDate}
                onChange={(d) => setActualDumpDate(d)}
              />
              <InputNumber
                placeholder="放罐产量 (kg)"
                style={{ width: '100%' }}
                min={0}
                precision={2}
                value={actualYieldKg}
                onChange={(v) => setActualYieldKg(v)}
              />
            </>
          )}
          {canFerm && (
            <Input.TextArea
              placeholder="备注（可选，如：染菌批）"
              rows={2}
              maxLength={255}
              value={actualRemark}
              onChange={(e) => setActualRemark(e.target.value)}
            />
          )}
        </Space>
        <Text type="secondary" style={{ fontSize: 12 }}>
          同一批次重复录入会更新原记录；保存后看板图表立即刷新。
        </Text>
      </Modal>
      {/* 本月计划产能设置弹窗 */}
      <Modal
        title={`设置本月计划产能：${board?.period.label ?? ''}`}
        open={capacityModalOpen}
        onOk={() => void submitCapacity()}
        onCancel={() => setCapacityModalOpen(false)}
        okText="保存"
        cancelText="取消"
      >
        <InputNumber
          placeholder="本月计划产能 (kg)"
          style={{ width: '100%' }}
          min={0}
          step={1000}
          value={capacityKg}
          onChange={(v) => setCapacityKg(v)}
        />
        <Text type="secondary" style={{ fontSize: 12 }}>
          按当前扎帐月保存；输入 310000 表示 310 吨。留空保存则清除设置。
        </Text>
      </Modal>

      {/* 底部：生产车间入口 */}
      <Card title="生产车间" variant="borderless" className="shadow-sm">
        <Row gutter={[12, 12]}>
          {workshopItems.map((item) => (
            <Col span={8} key={item.key}>
              <div
                data-testid={`workshop-entry:${item.key}`}
                className="h-full p-4 rounded-lg border border-[var(--color-hairline)] hover:border-[var(--color-primary)] cursor-pointer transition-colors"
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
