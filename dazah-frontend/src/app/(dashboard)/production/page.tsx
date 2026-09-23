'use client'

// 发酵车间生产实时看板（生产管理概览页，一期：计划驱动）
// 数据源：最新排产 Excel 存档（当前扎帐周期块）+ 人工检修标注。
// 实际完成/收率/合格率等指标待实际数据接入后启用（当前显示 --）。

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import {
  Alert,
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
  DatabaseOutlined,
  PlusOutlined,
  EditOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import ReactECharts from 'echarts-for-react'
import BoardNavBlocks from '@/components/production/board-nav-blocks'
import BatchProgressBar from '@/components/production/batch-progress-bar'
import FlBoardView from '@/components/production/FlBoardView'
import ProductionSummary from '@/components/production/production-summary'
import SalesPlanCard from '@/components/production/sales-plan-card'
import LineStatusConfirmModal, {
  LineHaltHistoryModal,
} from '@/components/production/line-status-confirm-modal'
import { useProductContextStore } from '@/stores/product-context'
import { useAuthStore } from '@/stores/auth'
import {
  hasProductionOverviewStage,
  PRODUCTION_PAGE_KEYS,
  useProductionPermissions,
} from '@/components/production/useProductionPermissions'
import {
  getFermentationBoard,
  markTankMaintenance,
  removeTankMaintenance,
  getFermentationBatchActuals,
  upsertFermentationBatchActual,
  deleteFermentationBatchActual,
  setFermentationMonthCapacity,
  getPlans,
  getProductionLineStatus,
  setProductionLineStatus,
} from '@/actions/production'
import type {
  FermentationBoard,
  BoardTank,
  FermentationBatchActual,
  FermentationBatchActualFormData,
  ProductionPlan,
} from '@/types/production'

const { Title, Text } = Typography

const REFRESH_INTERVAL_MS = 5 * 60 * 1000

// 提炼计划产量卡的下拉选择记忆（按月份存 {月份: "车间|产品"}），刷新后恢复
const PLAN_SELECTION_STORAGE_KEY = 'dazah.production.plan-card.selection'

// 产品 Tab 代码 → 展示名（导航块/看板标题）；系统代码 MC 的展示名
// 统一为霉酚酸（计划产量行按源数据名过滤，见 PLAN_PRODUCT_NAMES）。
// 氟苯尼考导航块展示短名，看板标题等空间充足处展示全名
const PRODUCT_NAMES: Record<string, string> = {
  SUMMARY: '汇总',
  FA: 'L-苯丙氨酸',
  MC: '霉酚酸',
  LN: '盐酸林可霉素',
  DR: '多拉菌素',
  LV: '洛伐他汀',
  MV: '美伐他汀',
  TY: 'L-色氨酸',
  FL: '2%氟苯尼考预混剂',
}
// 计划产量行的源数据产品名（production_plans.product_name）：
// 霉酚酸的源数据名不是 MC，计划卡过滤须用源名，与展示名分离。
// TY/FL/LN 的产销计划源名按产品名录入，待生产计划同步覆盖后自动匹配
const PLAN_PRODUCT_NAMES: Record<string, string> = {
  FA: 'L-苯丙氨酸',
  MC: '霉酚酸',
  LN: '盐酸林可霉素',
  DR: '多拉菌素',
  LV: '洛伐他汀',
  MV: '美伐他汀',
  TY: 'L-色氨酸',
  FL: '2%氟苯尼考预混剂',
}

function fmtDateTime(value?: string | null): string {
  if (!value) return '--'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '--'
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

/** 每秒时钟独立成小组件：定时器只重渲染自身，
 *  不触发整页重渲染（否则月份面板会被每秒新造的 value 对象拉回当月） */
function SystemClock() {
  const [clock, setClock] = useState('')
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
  return <Text type="secondary">系统时间：{clock}</Text>
}

function fmtShort(value?: string | null): string {
  // 纯日期字符串（如计划放罐日期）直接截取，避免 Date 按 UTC 解析产生时区偏移
  if (!value) return '-'
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
  const { message } = App.useApp()
  const productionUser = useAuthStore((state) => state.user)
  const { canOperate, canDelete } = useProductionPermissions(PRODUCTION_PAGE_KEYS.overview)
  // 工段数据权限：发酵模块挂发酵权限，提炼汇总挂提炼权限，收率需双权限；
  // 概览页授权用户按页面数据范围（production_fermentation/extraction/all）解析
  const canFerm = hasProductionOverviewStage(productionUser, 'fermentation')
  const canExtract = hasProductionOverviewStage(productionUser, 'extraction')
  const [board, setBoard] = useState<FermentationBoard | null>(null)
  const [boardMessage, setBoardMessage] = useState<string>('')
  const [loading, setLoading] = useState(true)
  // 产线停产状态：停产产品代码集合（全平台共享，人工切换，不自动恢复）
  const [haltedLines, setHaltedLines] = useState<string[]>([])
  // 停产切换确认：pendingHalted 为目标状态（null=关闭）；倒计时在确认框组件内
  const [haltPending, setHaltPending] = useState<boolean | null>(null)
  const [haltHistoryOpen, setHaltHistoryOpen] = useState(false)
  // 周期回看：空串 = 今天所在周期；否则为所选周期内任意日期
  // 当前产品上下文（导航块切换），看板按此产品取数；
  // SUMMARY 为汇总视图（五产线聚合），非单一产品
  const productCode = useProductContextStore((s) => s.productCode)
  // 查看月份按视图（产品 Tab / 汇总）各自独立，互不联动；
  // 会话内记住各自的月份，刷新后回到当月（'' = 当月）
  const [viewDateMap, setViewDateMap] = useState<Record<string, string>>({})
  const viewDate = viewDateMap[productCode] ?? ''
  const setViewDate = (value: string) =>
    setViewDateMap((prev) => ({ ...prev, [productCode]: value }))
  const isSummaryView = productCode === 'SUMMARY'
  // FL 氟苯尼考为合成预混工艺：无发酵工段，概览渲染独立批次工序看板
  const isFlView = productCode === 'FL'
  // FL 视图刷新信号：页面「立即刷新」按钮驱动（发酵视图走 loadBoard）
  const [flRefreshKey, setFlRefreshKey] = useState(0)
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
        // 未覆盖骨架（covered=false）时保留后端提示，卡片以空值兜底渲染
        setBoardMessage(
          res.data && res.data.covered === false
            ? res.message || ''
            : res.data
              ? ''
              : res.message || '',
        )
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
    if (isSummaryView || isFlView) return // 汇总无单产品看板；FL 走独立视图自取数
    void loadBoard() // eslint-disable-line react-hooks/set-state-in-effect -- 看板初始加载，与 201-1 页面既有模式一致
    const timer = setInterval(() => void loadBoard(), REFRESH_INTERVAL_MS)
    return () => clearInterval(timer)
  }, [loadBoard, isSummaryView, isFlView])

  // 产线停产状态：进入页面拉一次，切换确认后本地即时更新
  const loadHaltedLines = useCallback(async () => {
    try {
      const res = await getProductionLineStatus()
      if (res.code === 200 && res.data) {
        setHaltedLines(res.data.halted ?? [])
      }
    } catch {
      // 状态拉取失败不阻塞看板，仅无法显示停产标记
    }
  }, [])

  useEffect(() => {
    void loadHaltedLines() // eslint-disable-line react-hooks/set-state-in-effect -- 页面初始加载
  }, [loadHaltedLines])

  // 当前产品是否停产中
  const isHalted = !isSummaryView && haltedLines.includes(productCode)

  const openHaltConfirm = (target: boolean) => {
    setHaltPending(target)
  }

  const applyHaltChange = async (reason = '') => {
    if (haltPending === null) return
    const target = haltPending
    setHaltPending(null)
    try {
      const res = await setProductionLineStatus(target, productCode, reason)
      if (res.code === 200) {
        setHaltedLines((prev) =>
          target
            ? prev.includes(productCode)
              ? prev
              : [...prev, productCode]
            : prev.filter((code) => code !== productCode),
        )
        message.success(res.message || '状态已更新')
      } else {
        message.error(res.message || '状态更新失败')
      }
    } catch {
      message.error('状态更新失败')
    }
  }

  // 提炼计划产量：跟随概览自然月拉生产计划；选择按月记入本地存储，
  // 页面刷新后恢复所选行，仅当该行不在当月数据时才回退第一行
  // 计划行按当前产品 Tab 过滤：每个产品的下拉只列自己的车间行，选择互不影响
  const currentProductName =
    PLAN_PRODUCT_NAMES[productCode] ?? PLAN_PRODUCT_NAMES.FA
  const productPlanRows = useMemo(
    () => planRows.filter((r) => r.product_name === currentProductName),
    [planRows, currentProductName],
  )
  // 记忆键按 产品|月份 隔离
  const planMemoryKey = `${productCode}|${planMonth}`

  useEffect(() => {
    let cancelled = false
    void (async () => {
      let remembered = ''
      try {
        const store = JSON.parse(
          window.localStorage.getItem(PLAN_SELECTION_STORAGE_KEY) || '{}',
        )
        remembered =
          typeof store[planMemoryKey] === 'string' ? store[planMemoryKey] : ''
      } catch {
        // 存储不可用则当作无记录
      }
      try {
        const res = await getPlans({ month: planMonth, page_size: 200 })
        if (res.code === 200 && !cancelled) {
          const allRows = res.data || []
          setPlanRows(allRows)
          const rows = allRows.filter(
            (r) => r.product_name === currentProductName,
          )
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
  }, [planMonth, productCode, currentProductName, planMemoryKey])

  // 显式选择时写入本地存储（按产品+月份分开记忆）
  const handlePlanSelect = useCallback(
    (key: string) => {
      setSelectedPlanKey(key)
      try {
        const raw = window.localStorage.getItem(PLAN_SELECTION_STORAGE_KEY)
        const store = raw ? JSON.parse(raw) : {}
        store[planMemoryKey] = key
        window.localStorage.setItem(
          PLAN_SELECTION_STORAGE_KEY,
          JSON.stringify(store),
        )
      } catch {
        // 存储不可用时仅当次会话生效
      }
    },
    [planMemoryKey],
  )

  const submitMaintenance = async () => {
    if (!canOperate) return
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
    if (!canDelete) return
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
        board?.period?.start,
        board?.period?.end,
        productCode,
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
    if (!canOperate) return
    setEditingActual(item)
    setActualBatchNo(item?.batch_no ?? '')
    setActualDumpDate(item?.dump_date ? dayjs(item.dump_date) : null)
    setActualYieldKg(item?.yield_kg ?? null)
    setActualRemark(item?.remark ?? '')
    setActualModalOpen(true)
  }

  const submitActual = async () => {
    if (!canOperate) return
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
    const res = await upsertFermentationBatchActual(payload, productCode)
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
    if (!canDelete) return
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
    if (!canOperate) return
    setCapacityKg(board?.month_planned_capacity_kg ?? null)
    setCapacityModalOpen(true)
  }

  const submitCapacity = async () => {
    if (!canOperate) return
    const res = await setFermentationMonthCapacity(capacityKg, productCode)
    if (res.code === 200) {
      message.success('已保存本月计划产能')
      setCapacityModalOpen(false)
      await loadBoard()
    } else {
      message.error(res.message || '保存失败')
    }
  }

  const kpi = board?.kpis
  const periodEnd = board?.period?.end
  // 月份选择器取值 memo 化：每次渲染新造 dayjs 对象会让 rc-picker 在
  // value 引用变化时把打开的面板拉回当月，导致跨年导航选错年
  const monthPickerValue = useMemo(() => {
    if (viewDate) return dayjs(viewDate)
    if (isSummaryView) return dayjs()
    if (periodEnd) return dayjs(periodEnd)
    return null
  }, [viewDate, isSummaryView, periodEnd])
  // 周期回看：写操作（检修、产能设置）仅当前扎帐月开放
  // FL 视图无扎帐周期概念：所选月即当月（viewDate 空）视为当前
  const isCurrent = isFlView ? !viewDate : (board?.is_current_period ?? true)
  const dash = '--'
  // 「提炼已出成品（仓储成品入库）」：当期仓储入库合计；仅接入产品有值
  const extractInboundKg = board?.extract_finished_inbound_kg ?? null
  // 「提炼计划产量」当前选中行（车间+产品，仅当前产品的行）
  const selectedPlan =
    productPlanRows.find((r) => planKey(r) === selectedPlanKey) ?? null
  // 取数间隙（切产品/切月）内 selectedPlanKey 可能仍是上一产品的行键，
  // 仅当它属于当前产品行时才回显，避免下拉短暂显示其它产品的「车间|产品」
  const selectedPlanKeyInProduct = productPlanRows.some(
    (r) => planKey(r) === selectedPlanKey,
  )
  // 完成率 = 已出成品 ÷ 当前选中行的计划产量，百分比保留两位小数
  const extractPlanRate =
    extractInboundKg != null && selectedPlan?.planned_yield
      ? `${((extractInboundKg / selectedPlan.planned_yield) * 100).toFixed(2)}%`
      : dash

  // 发酵罐实时状态：三台发酵罐 + 最近已放罐的一批（凑齐 4 批）
  // 行序按移种（进罐）时间先后；无移种时间的罐（凑数已放罐/空闲/检修）按罐号排最后
  const renderTanks = useMemo(() => {
    const rows: BoardTank[] = [...(board?.tanks || [])]
    const last = board?.recent?.[0]
    if (last && !rows.some((t) => t.status === 'dumped')) {
      rows.push({
        tank_no: last.tank_no || '已放罐批次',
        status: 'dumped',
        batch_no: last.batch_no,
        inoculate_at: last.inoculate_at ?? null,
        // 已完成批次：培养时长即计划总周期
        cultured_hours: last.cycle_hours ?? null,
        cycle_hours: last.cycle_hours ?? null,
        dump_at: last.dump_date,
        note: '该罐本批次放罐作业完成',
      })
    }
    rows.sort((a, b) => {
      const aTime = a.inoculate_at || ''
      const bTime = b.inoculate_at || ''
      if (aTime && bTime && aTime !== bTime) return aTime < bTime ? -1 : 1
      if (aTime && !bTime) return -1
      if (!aTime && bTime) return 1
      // 同移种时间或都无：退回批次顺序号，再退罐号
      const seqDiff =
        (batchSeqNo(a.batch_no) ?? Number.POSITIVE_INFINITY) -
        (batchSeqNo(b.batch_no) ?? Number.POSITIVE_INFINITY)
      if (seqDiff !== 0) return seqDiff
      return (a.tank_no || '').localeCompare(b.tank_no || '')
    })
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

  // 批次进度数据：已完成（产量已录）→ 待出产量（已放罐未录产量）→ 运行中 → 未开始
  // 四段统一「本周期计划放罐」口径（后端已收口）：未开始 = kpis.pending
  // （已排产、放罐在本周期内、尚未进罐），四段之和恒等于计划放罐数；
  // 跨周期放罐的在制罐不计入（罐状态板仍展示）。不可用「计划 − 其余」倒减：
  // 在制批次数超过计划放罐数时负数钳零会吞掉批次
  const doneWithYield = kpi?.done_with_yield ?? 0
  const yieldPending = kpi?.yield_pending ?? 0
  const runningCount = kpi?.running ?? 0
  const notStarted = kpi?.pending ?? 0
  const capacityMode = plannedCapacityKg != null && plannedCapacityKg > 0

  // 理论批次：按排产计划，截至今天应放罐的批次数（放罐日期已到期的计划批次）。
  // 后端 month_done_planned 即该口径；设备利用率 = 实际已放罐（已录产量）
  // ÷ 理论应放罐，封顶 100%
  const asOfLabel = isCurrent
    ? dayjs().format('MM-DD')
    : (board?.period?.end ?? '').slice(5).replace('-', '-')
  const theoryBatches = kpi?.month_done_planned ?? null
  const utilizationRate =
    theoryBatches && kpi?.done_with_yield != null
      ? Math.min(100, Math.round((kpi.done_with_yield / theoryBatches) * 100))
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
      sub: board?.period?.label,
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
      sub: `截至 ${asOfLabel} · 按排产计划`,
      span: 8,
      extra: {
        label: '发酵设备利用率',
        value: utilizationRate != null ? `${utilizationRate}%` : dash,
        sub: `实际已放罐 ${kpi?.done_with_yield ?? dash} ÷ 应放罐 ${theoryBatches ?? dash}`,
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
        ) : record.status === 'maintenance' && canDelete ? (
          <Button size="small" onClick={() => void releaseMaintenance(record)}>
            解除检修
          </Button>
        ) : canOperate ? (
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
        ) : null,
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
          {canOperate && <Button size="small" type="link" onClick={() => openActualModal(record)}>
            编辑
          </Button>}
          {canDelete && <Popconfirm
            title="删除后看板图表不再统计该批次，确认删除？"
            okText="删除"
            cancelText="取消"
            onConfirm={() => void removeActual(record)}
          >
            <Button size="small" type="link" danger>
              删除
            </Button>
          </Popconfirm>}
        </Space>
      ),
    },
  ]

  // 单批产量柱状图 + 平均产量标线
  // 平均线优先用后端口径（DR：大罐批均值，中试线小罐批不计入），
  // 无后端值时按柱子自算
  const trendOutputs = board?.trend?.outputs ?? []
  const trendAvg =
    board?.trend?.avg_yield_kg ??
    (trendOutputs.length
      ? trendOutputs.reduce((sum, value) => sum + value, 0) / trendOutputs.length
      : null)

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

  // 告警跑马灯恒速：按内容实测宽度换算动画时长（速度 130px/s，最短 8s）。
  // 轨迹为 100% → -100%（两倍内容宽），故时长 = 2 × 宽度 ÷ 速度
  const marqueeRef = useRef<HTMLDivElement | null>(null)
  const [marqueeDuration, setMarqueeDuration] = useState(24)
  useLayoutEffect(() => {
    const el = marqueeRef.current
    if (!el) return
    const measure = () => {
      const w = el.scrollWidth
      if (w > 0) setMarqueeDuration(Math.max(8, (2 * w) / 130))
    }
    measure()
    if (typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [alertText])

  return (
    <div className="p-4 flex flex-col gap-3">
      {/* 顶部导航块：第 4 位为当前产品 L-苯丙氨酸，第 5/6 位洛伐他汀/美伐他汀
          （复用 MP 管线），首位为汇总 Tab（原地切换五产线聚合视图） */}
      <BoardNavBlocks />

      {/* 顶部标题卡：汇总态标题切换、单产品操作按钮隐藏 */}
      <Card
        variant="borderless"
        className="shadow-sm"
        styles={{ body: { padding: '12px 20px' } }}
      >
        <div className="flex items-center justify-between flex-wrap gap-2">
          <Space size={12}>
            <ScheduleOutlined style={{ fontSize: 22, color: '#1677ff' }} />
            <Title level={4} style={{ margin: 0 }}>
              {isSummaryView
                ? '生产汇总'
                : `${PRODUCT_NAMES[productCode] ?? PRODUCT_NAMES.FA}生产线`}
            </Title>
            {/* 生产线状态：生产中(绿)/停产中(红) 二态切换（仅概览操作权限可改）。
                选项 label 为带色点节点，选中值与下拉项同款颜色 */}
            {!isSummaryView && (
              <Button
                size="small"
                type="text"
                data-testid="halt-history-entry"
                onClick={() => setHaltHistoryOpen(true)}
              >
                停产历史
              </Button>
            )}
            {!isSummaryView && (
              <Select
                size="small"
                style={{ width: 104 }}
                data-testid="line-status-select"
                value={isHalted ? 'halted' : 'running'}
                disabled={!canOperate}
                onChange={(value) =>
                  openHaltConfirm(value === 'halted')
                }
                options={[
                  {
                    value: 'running',
                    label: (
                      <span
                        data-testid="line-status-label:running"
                        className="flex items-center gap-2"
                      >
                        <span
                          style={{
                            width: 8,
                            height: 8,
                            borderRadius: 4,
                            background: '#52c41a',
                          }}
                        />
                        生产中
                      </span>
                    ),
                  },
                  {
                    value: 'halted',
                    label: (
                      <span
                        data-testid="line-status-label:halted"
                        className="flex items-center gap-2"
                      >
                        <span
                          style={{
                            width: 8,
                            height: 8,
                            borderRadius: 4,
                            background: '#cf1322',
                          }}
                        />
                        停产中
                      </span>
                    ),
                  },
                ]}
              />
            )}
            <DatePicker
              size="small"
              picker="month"
              allowClear={false}
              style={{ width: 96 }}
              value={monthPickerValue}
              onChange={(d) => {
                // 选自然月 → 定位到主要落在该月的扎帐周期（该月 15 日必在其中）
                if (d) setViewDate(d.date(15).format('YYYY-MM-DD'))
              }}
            />
            {board?.period && !isSummaryView && !isFlView && (
              <Tag color="blue">生产周期 {board.period.label}</Tag>
            )}
            {!isCurrent && !isSummaryView && (
              <Button size="small" onClick={() => setViewDate('')}>
                回到本月
              </Button>
            )}
          </Space>
          <Space size={16}>
            <SystemClock />
            {!isSummaryView && !isHalted && (
              <Text type="secondary">数据刷新：5 分钟</Text>
            )}
            {!isSummaryView && !isHalted && (
              <>
                {!isFlView && (
                  <Button
                    size="small"
                    icon={<DatabaseOutlined />}
                    onClick={() => void openActuals()}
                  >
                    历史数据
                  </Button>
                )}
                <Button
                  size="small"
                  icon={
                    <SyncOutlined
                      spin={loading && !isFlView}
                    />
                  }
                  onClick={() => {
                    // FL 视图无发酵看板可拉，刷新信号交给独立视图
                    if (isFlView) setFlRefreshKey((k) => k + 1)
                    else void loadBoard()
                  }}
                >
                  立即刷新
                </Button>
              </>
            )}
          </Space>
        </div>
      </Card>

      {/* 停产占位：收起全部看板卡片，整页仅保留标题卡（含状态下拉与恢复入口） */}
      {isHalted && (
        <Card variant="borderless" className="shadow-sm">
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <span style={{ fontSize: 16 }}>
                该产品生产线停产中
              </span>
            }
          />
        </Card>
      )}

      {/* 汇总视图：五产线聚合表 + 播报汇总 */}
      {isSummaryView && (
        <>
          <ProductionSummary month={planMonth} />
          {/* 产销计划卡：销售计划执行表（飞书同步），跟随概览月份切换 */}
          <SalesPlanCard month={planMonth} />
        </>
      )}

      {/* FL 氟苯尼考看板：独立批次工序流转视图（无发酵模块，不拉排产存档） */}
      {!isSummaryView && !isHalted && isFlView && (
        <FlBoardView month={planMonth} refreshKey={flRefreshKey} />
      )}

      {/* 产品看板：停产中整块收起（数据保留在库，恢复生产即原样回来） */}
      {!isSummaryView && !isHalted && !isFlView && (
      <>
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
              ref={marqueeRef}
              style={{
                display: 'inline-block',
                whiteSpace: 'nowrap',
                animation: `board-marquee ${marqueeDuration}s linear infinite`,
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
        /* 卡体随卡定高：内容（占位框 height:100%）以 body 高度解析，
           否则 body 被内容撑破卡片、占位虚线框被裁断 */
        .extraction-summary-row .ant-card-body {
          height: 100%;
          overflow: hidden;
        }
        .extraction-summary-row .extraction-rate-placeholder {
          min-height: 0;
        }
      `}</style>

      {/* 主体：卡片框架对所有产品一致，数值按数据有无落位；
          无排产存档时仅显示警示条，卡片以空值兜底渲染 */}
      {loading && !board ? (
        <Card variant="borderless" className="shadow-sm">
          <Empty description="看板加载中…" />
        </Card>
      ) : (
        <>
          {boardMessage && (
            <Alert
              type="warning"
              showIcon
              data-testid="board-message"
              title={
                board?.covered === false && !isHalted
                  ? `${boardMessage}；如该产线实际已停产，可将产线状态标记为停产。`
                  : boardMessage
              }
            />
          )}
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
                           {card.extra.editable &&
                            board?.covered !== false &&
                            isCurrent &&
                            canOperate && (
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
                        value={
                          selectedPlanKeyInProduct ? selectedPlanKey : undefined
                        }
                        onChange={handlePlanSelect}
                        placeholder="车间 · 产品"
                        style={{ width: 168, fontSize: 12 }}
                        options={productPlanRows.map((r) => ({
                          value: planKey(r),
                          label: `${r.workshop ?? ''} ${r.product_name}`,
                        }))}
                        disabled={productPlanRows.length === 0}
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
                      {productPlanRows.length === 0
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
                            ? `${PRODUCT_NAMES[productCode] ?? PRODUCT_NAMES.FA} · 本月合计(kg)`
                            : board && board.covered !== false
                              ? '数据源待接入'
                              : '上传排产后按周期统计'}
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
                    {/* 占位卡：内容待后续接入 */}
                    <div className="extraction-rate-placeholder">
                      <Empty
                        description="待接入"
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
                <Text strong>{isCurrent ? '本月发酵进度' : '历史发酵进度'}</Text>
                {!isCurrent && <Tag color="orange">历史周期</Tag>}
              </div>
              {!capacityMode && isCurrent && (
                <Text type="secondary" style={{ fontSize: 12 }}>
                  未设置计划产能，进度暂按批次数展示；请编辑「本月计划产能」后切换产能口径
                </Text>
              )}
            </div>
            <BatchProgressBar
              doneCount={doneWithYield}
              pendingCount={yieldPending}
              runningCount={runningCount}
              idleCount={notStarted}
              doneYieldKg={doneYieldKg}
              plannedCapacityKg={plannedCapacityKg}
              historical={!isCurrent}
            />
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
      </>)
      }

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
        size={640}
        open={actualsOpen}
        onClose={() => setActualsOpen(false)}
        extra={canOperate ? <Button
            type="primary"
            size="small"
            icon={<PlusOutlined />}
            onClick={() => openActualModal(null)}
          >
            录入批次产量
          </Button> : null}
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
        open={actualModalOpen && canOperate}
        onOk={canOperate ? () => void submitActual() : undefined}
        onCancel={() => setActualModalOpen(false)}
        okText="保存"
        cancelText="取消"
      >
        <Space orientation="vertical" style={{ width: '100%' }} size={12}>
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
        title={`设置本月计划产能：${board?.period?.label ?? ''}`}
        open={capacityModalOpen && canOperate}
        onOk={canOperate ? () => void submitCapacity() : undefined}
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
      {/* 生产线状态切换确认：确认按钮 5 秒倒计时后才可点，取消随时可点 */}
      <LineStatusConfirmModal
        productName={PRODUCT_NAMES[productCode] ?? PRODUCT_NAMES.FA}
        productCode={productCode}
        pendingHalted={haltPending}
        onCancel={() => setHaltPending(null)}
        onConfirm={(reason) => void applyHaltChange(reason)}
        onOpenHistory={() => setHaltHistoryOpen(true)}
      />
      {/* 停产历史独立查看入口：完整时间线，只读，不触发状态切换 */}
      <LineHaltHistoryModal
        productCode={productCode}
        productName={PRODUCT_NAMES[productCode] ?? PRODUCT_NAMES.FA}
        open={haltHistoryOpen}
        onClose={() => setHaltHistoryOpen(false)}
      />
    </div>
  )
}
