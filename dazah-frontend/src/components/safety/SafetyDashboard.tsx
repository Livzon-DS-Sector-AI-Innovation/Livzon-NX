'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Button, Card, Row, Col, Typography, Space, Tag, Drawer, Segmented, Table } from 'antd'
import {
  WarningOutlined,
  RobotOutlined,
  ArrowRightOutlined,
  CheckCircleOutlined,
  AlertOutlined,
  ClockCircleOutlined,
  EnvironmentOutlined,
  UserOutlined,
  TeamOutlined,
  ExperimentOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import type { SpecialOperationReport, DailyRiskReport, TrainingRecord } from '@/types/safety'
import type { SafetyOverviewData, ChemicalInventoryItem } from '@/actions/safety'
import SafetyOverviewMap from './SafetyOverviewMap'
import PlatformNotice from '@/components/shared/PlatformNotice'

const { Title, Text } = Typography

// ── Types ──

export interface DashboardData {
  openHazardCount: number
  /** 未关闭隐患明细（默认来源 24小时值班隐患），供卡片抽屉展示 */
  openHazardRecords?: Array<{ record_id: string; fields: Record<string, unknown> }>
  unfinishedIdentCount: number
  /** 未完成辨识明细，供卡片抽屉展示 */
  unfinishedIdentifications?: Array<{
    id: string
    hazard_id_no: string
    department: string
    overall_status: string
  }>
  expiringCerts: TrainingRecord[]
  todaySpecialOps: SpecialOperationReport[]
  todayDailyRisks: DailyRiskReport[]
  overview: SafetyOverviewData | null
  /** 危化品车间存量（危化品管理数据），用于“危化品每日统计”卡片 */
  chemicalInventories: ChemicalInventoryItem[]
}

/** 驾驶舱底部两张卡片固定高度，内容超出时在卡片内滚动 */
const PANEL_HEIGHT = 420
// 半宽下的作业行栅格：作业内容 / 等级 / 作业地点(含部门) / 负责人 / 时段 / 来源
const RISK_GRID = 'minmax(0,1.1fr) 44px minmax(0,1.15fr) 58px 66px 54px'
// 危化品行栅格：车间 / 物料 / 现有量 / 临界量 / 是否超标
const CHEM_GRID = 'minmax(0,0.9fr) minmax(0,1.2fr) 62px 62px 58px'

interface TodayRiskRow {
  key: string
  source: 'special_op' | 'daily_risk'
  sourceLabel: string
  operationType: string
  operationDescription: string
  riskLevel: string
  location: string
  department: string
  responsiblePerson: string
  timeRange: string
  status: string
}

// ── DESIGN.md Token Colors ──

const T = {
  primary: '#5645d4',
  error: '#E03131',
  warning: '#DD5B00',
  success: '#1AAE39',
  ink: '#1a1a1a',
  charcoal: '#37352f',
  slate: '#5d5b54',
  steel: '#787671',
  muted: '#bbb8b1',
  hairline: '#e5e3df',
  surface: '#f6f5f4',
  canvas: '#ffffff',
  peach: '#ffe8d4',
  rose: '#fde0ec',
  mint: '#d9f3e1',
  lavender: '#e6e0f5',
  sky: '#dcecfa',
  yellow: '#fef7d6',
  yellowBold: '#f9e79f',
  gray: '#f0eeec',
}

// ── Operation type labels ──

const OP_TYPE_LABELS: Record<string, string> = {
  hot_work: '动火作业',
  confined_space: '受限空间',
  height_work: '高处作业',
  temporary_electricity: '临时用电',
  blind_plate: '盲板抽堵',
  excavation: '动土作业',
  lifting: '起重吊装',
  pipeline: '管线打开',
}

function opTypeLabel(type: string): string {
  return OP_TYPE_LABELS[type] || type
}

// ── Risk level config ──

function riskLevelConfig(level?: string): { color: string; bg: string; label: string } {
  const l = level ?? ''
  if (l.includes('一') || l.includes('重大') || l.includes('1')) {
    return { color: '#DC2626', bg: '#fef2f2', label: l || '一级' }
  }
  if (l.includes('二') || l.includes('较大') || l.includes('2')) {
    return { color: '#F97316', bg: '#fff7ed', label: l || '二级' }
  }
  if (l.includes('三') || l.includes('一般') || l.includes('3')) {
    return { color: '#CA8A04', bg: '#fefce8', label: l || '三级' }
  }
  if (l.includes('四') || l.includes('低') || l.includes('4')) {
    return { color: '#16A34A', bg: '#f0fdf4', label: l || '四级' }
  }
  return { color: T.steel, bg: T.surface, label: l || '-' }
}

// ── Certificate expiry status ──

function certExpiryTag(expiry?: string): { color: string; bg: string; text: string } {
  if (!expiry) return { color: T.steel, bg: T.surface, text: '未知' }
  const days = Math.ceil((new Date(expiry).getTime() - Date.now()) / 86400000)
  if (days < 0) return { color: '#DC2626', bg: '#fef2f2', text: '已过期' }
  if (days <= 7) return { color: '#F97316', bg: '#fff7ed', text: `${days}天后到期` }
  return { color: '#CA8A04', bg: '#fefce8', text: `${days}天后到期` }
}

// ═══════════════════════════════════════════════════════════════
// KPI Card (clickable)
// ═══════════════════════════════════════════════════════════════

function KpiCard({
  label,
  value,
  suffix,
  color,
  bg,
  icon,
  onClick,
  headerExtra,
}: {
  label: string
  value: number
  suffix?: string
  color: string
  bg: string
  icon: React.ReactNode
  onClick?: () => void
  /** 卡片头部行内嵌控件（如来源切换器） */
  headerExtra?: React.ReactNode
}) {
  return (
    <div
      onClick={onClick}
      className="rounded-xl p-5 border transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md group"
      style={{
        backgroundColor: T.canvas,
        borderColor: T.hairline,
        borderRadius: 12,
        cursor: onClick ? 'pointer' : 'default',
      }}
    >
      <div className="flex items-start justify-between mb-3 gap-2">
        <Text
          className="text-xs font-semibold uppercase tracking-wider"
          style={{ color: T.slate, fontSize: 11, letterSpacing: '0.5px' }}
        >
          {label}
        </Text>
        <div className="flex items-center gap-2 flex-shrink-0">
          {headerExtra}
          <div
            className="w-9 h-9 rounded-lg flex items-center justify-center text-base"
            style={{ backgroundColor: bg, color }}
          >
            {icon}
          </div>
        </div>
      </div>
      <div className="flex items-baseline justify-between">
        <div className="flex items-baseline gap-1">
          <span
            className="text-3xl font-semibold tracking-tight"
            style={{ color, fontFamily: 'var(--font-ui)' }}
          >
            {value}
          </span>
          {suffix && (
            <span className="text-sm" style={{ color: T.steel }}>
              {suffix}
            </span>
          )}
        </div>
        {onClick && (
          <ArrowRightOutlined
            className="opacity-0 group-hover:opacity-100 transition-opacity duration-200"
            style={{ color: T.muted, fontSize: 12 }}
          />
        )}
      </div>
    </div>
  )
}

// 未关闭隐患卡片的数据来源：24小时值班隐患 / 隐患台账（均为飞书镜像表）
type OpenHazardSource = 'duty' | 'ledger'
const OPEN_HAZARD_SOURCES: Record<
  OpenHazardSource,
  {
    label: string
    pageKey: string
    statusField: string
    closedValue: string
    /** 只统计当年的记录时使用的日期字段（隐患台账的检查日期） */
    yearDateField?: string
  }
> = {
  duty: {
    label: '24小时隐患',
    pageKey: 'safety:risk-hazard:hazard-inspection:hazard-duty',
    statusField: '整改情况',
    closedValue: '已整改',
  },
  ledger: {
    label: '隐患台账',
    pageKey: 'safety:risk-hazard:hazard-inspection:hazard-quick-report',
    statusField: '关闭状态',
    closedValue: '已关闭',
    yearDateField: '检查内容',
  },
}
const HAZARD_SOURCE_META_LABEL = (source: OpenHazardSource) =>
  OPEN_HAZARD_SOURCES[source].label

interface OpenHazardRow {
  record_id: string
  content: string
  where: string
  who: string
  date: string
  status: string
}

function extractText(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value
  if (Array.isArray(value)) {
    return value
      .map((item) =>
        typeof item === 'object' && item !== null && 'name' in item
          ? String((item as { name: unknown }).name)
          : String(item)
      )
      .join('、')
  }
  return String(value)
}

function toOpenHazardRow(
  record: { record_id: string; fields: Record<string, unknown> },
  source: OpenHazardSource
): OpenHazardRow {
  const fields = record.fields ?? {}
  const duty = source === 'duty'
  return {
    record_id: record.record_id,
    content: extractText(fields['隐患内容']),
    where: extractText(fields[duty ? '车间/位置' : '部门/车间']),
    who: extractText(fields[duty ? '值班人员' : '负责人']),
    date: extractText(fields[duty ? '值班日期' : '目标完成日期']),
    status: extractText(fields[OPEN_HAZARD_SOURCES[source].statusField]),
  }
}

// ═══════════════════════════════════════════════════════════════
// Main Dashboard
// ═══════════════════════════════════════════════════════════════

export default function SafetyDashboard({ data }: { data: DashboardData }) {
  const router = useRouter()
  const [certDrawerOpen, setCertDrawerOpen] = useState(false)

  // 未关闭隐患：数据来源可切换（24小时值班隐患 / 隐患台账）
  const [hazardSource, setHazardSource] = useState<OpenHazardSource>('duty')
  const [openHazardCount, setOpenHazardCount] = useState(data.openHazardCount)
  const [openHazardRows, setOpenHazardRows] = useState<OpenHazardRow[]>(
    (data.openHazardRecords ?? []).map((row) => toOpenHazardRow(row, 'duty'))
  )
  const [hazardLoading, setHazardLoading] = useState(false)
  const [hazardDrawerOpen, setHazardDrawerOpen] = useState(false)
  const [identDrawerOpen, setIdentDrawerOpen] = useState(false)

  const unfinishedIdents = useMemo(
    () =>
      (data.unfinishedIdentifications ?? []).map((item) => ({
        ...item,
        statusLabel:
          item.overall_status === 'draft' ? '草稿' : '进行中',
      })),
    [data.unfinishedIdentifications]
  )

  const loadOpenHazards = async (source: OpenHazardSource) => {
    const conf = OPEN_HAZARD_SOURCES[source]
    setHazardLoading(true)
    try {
      // 数量：统计接口按状态字段分组（neq 已关闭/已整改）
      const yearConditions =
        conf.yearDateField && source === 'ledger'
          ? [
              {
                field: conf.yearDateField,
                op: 'gte' as const,
                value: `${new Date().getFullYear()}-01-01`,
              },
            ]
          : []
      const [statsRes, detailsRes] = await Promise.all([
        import('@/actions/safety').then((m) =>
          m.getSafetyPageTableStats({
            pageKey: conf.pageKey,
            groupBy: [conf.statusField],
            conditions: [
              { field: conf.statusField, op: 'neq', value: conf.closedValue },
              ...yearConditions,
            ],
          })
        ),
        import('@/actions/safety').then((m) =>
          m.getOpenHazardDetails({ source, limit: 50 })
        ),
      ])
      setOpenHazardCount(
        statsRes.code === 200 && statsRes.data ? statsRes.data.total : 0
      )
      if (detailsRes.code === 200 && detailsRes.data) {
        setOpenHazardRows(
          detailsRes.data.map((row) => ({
            record_id: row.record_id,
            content: row.content,
            where: row.where,
            who: row.who,
            date: row.date,
            status: row.status,
          }))
        )
      } else {
        setOpenHazardRows([])
      }
    } catch {
      setOpenHazardCount(0)
      setOpenHazardRows([])
    } finally {
      setHazardLoading(false)
    }
  }

  const hasAlerts = data.expiringCerts.length > 0

  // ── Certificate table columns ──

  const certColumns: ColumnsType<TrainingRecord> = [
    {
      title: '姓名',
      dataIndex: 'employee_name',
      key: 'name',
      width: 100,
      render: (v) => <Text style={{ color: T.charcoal }}>{v || '-'}</Text>,
    },
    {
      title: '部门',
      dataIndex: 'department',
      key: 'dept',
      width: 100,
      render: (v) => <Text style={{ color: T.steel }}>{v || '-'}</Text>,
    },
    {
      title: '岗位',
      dataIndex: 'position',
      key: 'position',
      width: 100,
      render: (v) => <Text style={{ color: T.steel }}>{v || '-'}</Text>,
    },
    {
      title: '证书编号',
      dataIndex: 'certificate_no',
      key: 'cert_no',
      width: 150,
      render: (v) => <Text style={{ color: T.charcoal, fontFamily: 'monospace' }}>{v || '-'}</Text>,
    },
    {
      title: '到期时间',
      dataIndex: 'certificate_expiry',
      key: 'expiry',
      width: 120,
      render: (v: string) => (
        <Text style={{ color: T.charcoal, fontWeight: 500 }}>
          {v ? new Date(v).toLocaleDateString('zh-CN') : '-'}
        </Text>
      ),
    },
    {
      title: '状态',
      dataIndex: 'certificate_expiry',
      key: 'status',
      width: 110,
      render: (v: string) => {
        const tag = certExpiryTag(v)
        return (
          <Tag
            style={{
              color: tag.color,
              backgroundColor: tag.bg,
              border: 'none',
              borderRadius: 6,
              fontSize: 11,
              fontWeight: 600,
            }}
          >
            {tag.text}
          </Tag>
        )
      },
    },
  ]

  // ── Today risk rows ──

  const todayRisks: TodayRiskRow[] = [
    ...data.todaySpecialOps.map((r) => {
      // 报备未填风险等级时回退作业级别（GB30871：特级/一级/二级）
      const levelText =
        r.risk_level ||
        { special: '特级', grade1: '一级', grade2: '二级', not_applicable: '不适用' }[
          r.operation_level
        ] ||
        ''
      const rl = riskLevelConfig(levelText)
      return {
        key: `so-${r.id}`,
        source: 'special_op' as const,
        sourceLabel: '特殊作业',
        operationType: opTypeLabel(r.operation_type),
        operationDescription: r.work_description || '-',
        riskLevel: rl.label,
        location: r.location || '-',
        department: r.department || '-',
        responsiblePerson: r.work_leader_name || r.guardian_name || '-',
        timeRange: [r.planned_start_time, r.planned_end_time]
          .filter(Boolean)
          .map((t) => (t ? new Date(t).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : ''))
          .join(' – ') || '-',
        status: r.status,
      }
    }),
    ...data.todayDailyRisks.map((r) => {
      const rl = riskLevelConfig(r.risk_level)
      return {
        key: `dr-${r.id}`,
        source: 'daily_risk' as const,
        sourceLabel: '每日报备',
        operationType: r.operation_description.slice(0, 12) + (r.operation_description.length > 12 ? '…' : ''),
        operationDescription: r.operation_description,
        riskLevel: rl.label,
        location: r.location || '-',
        department: r.department || '-',
        responsiblePerson: r.responsible_person || r.applicant_name || '-',
        timeRange: [r.planned_start_time, r.planned_end_time]
          .filter(Boolean)
          .map((t) => (t ? new Date(t).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : ''))
          .join(' – ') || '-',
        status: r.status,
      }
    }),
  ]

  const totalTodayRisks = todayRisks.length

  // 危化品每日统计：优先统计表镜像（飞书）全量行，未配置时回退本地车间存量
  const mirrorDaily = data.overview?.hazchem_daily ?? []
  const useMirror = mirrorDaily.length > 0
  const chemRows = useMirror
    ? mirrorDaily.map((r, i) => ({
        key: `m${i}`,
        workshop: r.workshop,
        name: r.chemical_name,
        quantity: r.quantity,
        upper: r.upper_limit,
        unit: r.unit || '吨',
        over: r.over_pct !== null && r.over_pct !== undefined,
        pct: r.over_pct,
      }))
    : (data.chemicalInventories ?? []).map((r) => ({
        key: r.id,
        workshop: r.workshop,
        name: r.chemical_name,
        quantity: r.quantity,
        upper: r.upper_limit,
        unit: r.unit,
        over: !!r.over_limit,
        pct: r.over_pct,
      }))
  const chemOverLimit = chemRows.filter((c) => c.over).length

  // ── Render ──

  return (
    <div className="space-y-6 pb-8">
      {/* ── Header ── */}
      <div>
        <Title level={4} className="!mb-1" style={{ fontFamily: 'var(--font-ui)' }}>
          安全管理总览
        </Title>
        <Text style={{ color: T.slate, fontSize: 14 }}>
          实时监控安全管理状态 · 保障安全生产
        </Text>
      </div>

      {/* ── Alert Banner ── */}
      {hasAlerts && (
        <div
          onClick={() => setCertDrawerOpen(true)}
          className="rounded-xl p-4 flex items-center gap-3 cursor-pointer transition-all duration-200 hover:-translate-y-0.5"
          style={{ backgroundColor: T.yellowBold, borderRadius: 12 }}
        >
          <ClockCircleOutlined style={{ color: T.warning, fontSize: 18 }} />
          <Text strong style={{ color: T.charcoal, fontSize: 14 }}>
            {data.expiringCerts.length} 个培训证书即将到期，点击查看详情
          </Text>
          <ArrowRightOutlined style={{ color: T.warning, marginLeft: 'auto' }} />
        </div>
      )}

      {/* ── KPI Cards Row ── */}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={8}>
          <KpiCard
            label="未关闭隐患"
            value={openHazardCount}
            suffix="条"
            color={openHazardCount > 0 ? T.warning : T.success}
            bg={openHazardCount > 0 ? T.peach : T.mint}
            icon={<WarningOutlined />}
            onClick={() => setHazardDrawerOpen(true)}
            headerExtra={
              <Segmented
                size="small"
                value={hazardSource}
                onChange={(v) => {
                  const next = v as 'duty' | 'ledger'
                  setHazardSource(next)
                  void loadOpenHazards(next)
                }}
                options={[
                  { label: '24小时', value: 'duty' },
                  { label: '台账', value: 'ledger' },
                ]}
              />
            }
          />
        </Col>
        <Col xs={24} sm={8}>
          <KpiCard
            label="即将到期证书"
            value={data.expiringCerts.length}
            suffix="张"
            color={data.expiringCerts.length > 0 ? T.error : T.success}
            bg={data.expiringCerts.length > 0 ? T.rose : T.mint}
            icon={<ClockCircleOutlined />}
            onClick={() => setCertDrawerOpen(true)}
          />
        </Col>
        <Col xs={24} sm={8}>
          <KpiCard
            label="危险源辨识未完成"
            value={data.unfinishedIdentCount}
            suffix="条"
            color={data.unfinishedIdentCount > 0 ? T.primary : T.success}
            bg={T.lavender}
            icon={<RobotOutlined />}
            onClick={() => setIdentDrawerOpen(true)}
          />
        </Col>
      </Row>

      {/* ── 厂区风险分区 · 当日分布（平面图落点） ── */}
      {data.overview && (
        <SafetyOverviewMap overview={data.overview} />
      )}

      {/* ── 超储物料 ── */}
      {data.overview && (data.overview.over_limit_chemicals ?? []).length > 0 && (
        <PlatformNotice
          type="warning"
          showRulesLink={false}
          message={
            <Text strong style={{ color: T.charcoal, fontSize: 14 }}>
              超储物料 {(data.overview.over_limit_chemicals ?? []).length} 项（存量 &gt; 上限）
            </Text>
          }
          description={
            <div className="mt-2 space-y-1">
              {(data.overview.over_limit_chemicals ?? []).map((chem) => (
                <div
                  key={chem.inventory_id}
                  className="flex items-center gap-3 text-sm"
                >
                  <Text style={{ color: T.charcoal, fontWeight: 500 }}>
                    {chem.chemical_name}
                  </Text>
                  <Text style={{ color: T.steel, fontSize: 12 }}>
                    {chem.workshop} · {chem.quantity}{chem.unit} / {chem.upper_limit ?? '-'}{chem.unit}
                  </Text>
                  {chem.over_pct !== null && (
                    <Tag
                      style={{
                        color: T.error,
                        backgroundColor: T.rose,
                        border: 'none',
                        borderRadius: 6,
                        fontSize: 11,
                        fontWeight: 600,
                      }}
                    >
                      超储 {chem.over_pct}%
                    </Tag>
                  )}
                </div>
              ))}
            </div>
          }
          className="!rounded-xl"
        />
      )}

      {/* ── 今日关键风险作业 + 危化品每日统计（半宽并排、等高固定、内部滚动） ── */}
      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card
            variant="borderless"
            className="!shadow-sm"
            style={{
              height: PANEL_HEIGHT,
              borderRadius: 12,
              border: `1px solid ${T.hairline}`,
              display: 'flex',
              flexDirection: 'column',
            }}
            styles={{
              body: { flex: 1, minHeight: 0, overflow: 'auto', padding: '12px 16px' },
            }}
            title={
              <Space>
                <AlertOutlined style={{ color: T.error }} />
                <Text strong style={{ fontSize: 15, color: T.charcoal }}>
                  今日关键风险作业
                </Text>
                {totalTodayRisks > 0 && (
                  <span
                    className="text-xs font-semibold px-2 py-0.5 rounded"
                    style={{ backgroundColor: T.rose, color: T.error, borderRadius: 6 }}
                  >
                    {totalTodayRisks} 项
                  </span>
                )}
              </Space>
            }
          >
            {totalTodayRisks === 0 ? (
              <div className="text-center py-8">
                <CheckCircleOutlined style={{ fontSize: 32, color: T.muted }} />
                <Text className="block mt-2" style={{ color: T.muted }}>
                  今日暂无风险作业
                </Text>
              </div>
            ) : (
              <>
                {/* 表头随滚动固定在顶部 */}
                <div
                  className="hidden md:grid gap-2 px-3 py-2 rounded-lg mb-1"
                  style={{
                    gridTemplateColumns: RISK_GRID,
                    backgroundColor: T.surface,
                    borderRadius: 8,
                    position: 'sticky',
                    top: 0,
                    zIndex: 1,
                  }}
                >
                  {['作业内容', '等级', '作业地点', '负责人', '时段', '来源'].map((h) => (
                    <Text key={h} className="text-xs font-semibold" style={{ color: T.slate, fontSize: 11 }}>
                      {h}
                    </Text>
                  ))}
                </div>

                <div className="space-y-1">
                  {todayRisks.map((row) => {
                    const rl = riskLevelConfig(row.riskLevel)
                    const isSpecialOp = row.source === 'special_op'
                    return (
                      <div
                        key={row.key}
                        className="grid gap-2 px-3 py-2 rounded-lg cursor-pointer transition-colors hover:bg-[var(--color-surface)] items-center"
                        style={{ borderRadius: 8, gridTemplateColumns: RISK_GRID }}
                        onClick={() => router.push(isSpecialOp ? '/safety/special-ops' : '/safety/risk-reporting')}
                      >
                        {/* 作业内容 */}
                        <div className="flex items-center gap-1.5 min-w-0">
                          <div
                            className="w-2 h-2 rounded-full flex-shrink-0"
                            style={{ backgroundColor: rl.color }}
                          />
                          <Text
                            className="text-xs truncate"
                            style={{ color: T.charcoal }}
                            title={row.operationDescription}
                          >
                            {row.operationType}
                          </Text>
                        </div>

                        {/* 等级 */}
                        <div className="flex items-center">
                          <Tag
                            style={{
                              color: rl.color,
                              backgroundColor: rl.bg,
                              border: 'none',
                              borderRadius: 6,
                              fontSize: 10,
                              fontWeight: 600,
                              margin: 0,
                            }}
                          >
                            {rl.label}
                          </Tag>
                        </div>

                        {/* 作业地点（副行显示部门） */}
                        <div className="min-w-0">
                          <div className="flex items-center gap-1 min-w-0">
                            <EnvironmentOutlined style={{ color: T.muted, fontSize: 10, flexShrink: 0 }} />
                            <Text
                              className="text-xs truncate"
                              style={{ color: T.steel }}
                              title={row.location}
                            >
                              {row.location}
                            </Text>
                          </div>
                          <div className="flex items-center gap-1 min-w-0">
                            <TeamOutlined style={{ color: T.muted, fontSize: 10, flexShrink: 0 }} />
                            <Text
                              className="truncate"
                              style={{ color: T.muted, fontSize: 11 }}
                              title={row.department}
                            >
                              {row.department}
                            </Text>
                          </div>
                        </div>

                        {/* 负责人/监护人 */}
                        <div className="flex items-center gap-1 min-w-0">
                          <UserOutlined style={{ color: T.muted, fontSize: 10, flexShrink: 0 }} />
                          <Text
                            className="text-xs truncate"
                            style={{ color: T.steel }}
                            title={row.responsiblePerson}
                          >
                            {row.responsiblePerson}
                          </Text>
                        </div>

                        {/* 时段 */}
                        <div className="flex items-center">
                          <Text style={{ color: T.steel, fontSize: 11 }}>{row.timeRange}</Text>
                        </div>

                        {/* 来源 */}
                        <div className="flex items-center">
                          <Tag
                            style={{
                              color: isSpecialOp ? '#1677ff' : '#722ed1',
                              backgroundColor: isSpecialOp ? T.sky : T.lavender,
                              border: 'none',
                              borderRadius: 6,
                              fontSize: 10,
                              fontWeight: 600,
                              margin: 0,
                            }}
                          >
                            {row.sourceLabel}
                          </Tag>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </>
            )}
          </Card>
        </Col>

        <Col xs={24} xl={12}>
          <Card
            variant="borderless"
            className="!shadow-sm"
            style={{
              height: PANEL_HEIGHT,
              borderRadius: 12,
              border: `1px solid ${T.hairline}`,
              display: 'flex',
              flexDirection: 'column',
            }}
            styles={{
              body: { flex: 1, minHeight: 0, overflow: 'auto', padding: '12px 16px' },
            }}
            title={
              <Space>
                <ExperimentOutlined style={{ color: T.primary }} />
                <Text strong style={{ fontSize: 15, color: T.charcoal }}>
                  危化品每日统计
                </Text>
                {chemRows.length > 0 && (
                  <span
                    className="text-xs font-semibold px-2 py-0.5 rounded"
                    style={{ backgroundColor: T.lavender, color: T.primary, borderRadius: 6 }}
                  >
                    {chemRows.length} 项
                    {chemOverLimit > 0 ? ` · 超标 ${chemOverLimit}` : ''}
                  </span>
                )}
              </Space>
            }
            extra={
              <Button type="link" size="small" onClick={() => router.push('/safety/hazchem')}>
                危化品管理
              </Button>
            }
          >
            {chemRows.length === 0 ? (
              <div className="text-center py-8">
                <Text className="block" style={{ color: T.muted }}>
                  暂无车间存量记录，可在「危化品管理」维护
                </Text>
              </div>
            ) : (
              <>
                {/* 表头随滚动固定在顶部 */}
                <div
                  className="hidden md:grid gap-2 px-3 py-2 rounded-lg mb-1"
                  style={{
                    gridTemplateColumns: CHEM_GRID,
                    backgroundColor: T.surface,
                    borderRadius: 8,
                    position: 'sticky',
                    top: 0,
                    zIndex: 1,
                  }}
                >
                  {['车间', '物料', '现有量', '临界量', '是否超标'].map((h) => (
                    <Text key={h} className="text-xs font-semibold" style={{ color: T.slate, fontSize: 11 }}>
                      {h}
                    </Text>
                  ))}
                </div>

                <div className="space-y-1">
                  {chemRows.map((row) => (
                    <div
                      key={row.key}
                      className="grid gap-2 px-3 py-2 rounded-lg items-center"
                      style={{
                        borderRadius: 8,
                        gridTemplateColumns: CHEM_GRID,
                        backgroundColor: row.over ? T.rose : 'transparent',
                      }}
                    >
                      <Text className="text-xs truncate" style={{ color: T.charcoal }} title={row.workshop}>
                        {row.workshop}
                      </Text>
                      <Text className="text-xs truncate" style={{ color: T.charcoal }} title={row.name}>
                        {row.name}
                      </Text>
                      <Text style={{ color: T.charcoal, fontSize: 12 }}>
                        {row.quantity}
                        {row.unit}
                      </Text>
                      <Text style={{ color: T.steel, fontSize: 12 }}>
                        {row.upper ?? '不限'}
                        {row.upper ? row.unit : ''}
                      </Text>
                      <div>
                        {row.over ? (
                          <Tag
                            style={{
                              color: T.error,
                              backgroundColor: T.canvas,
                              border: 'none',
                              borderRadius: 6,
                              fontSize: 10,
                              fontWeight: 700,
                              margin: 0,
                            }}
                          >
                            超标{row.pct !== null && row.pct !== undefined ? ` ${row.pct}%` : ''}
                          </Tag>
                        ) : (
                          <Tag
                            style={{
                              color: T.success,
                              backgroundColor: T.mint,
                              border: 'none',
                              borderRadius: 6,
                              fontSize: 10,
                              fontWeight: 600,
                              margin: 0,
                            }}
                          >
                            正常
                          </Tag>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </Card>
        </Col>
      </Row>

      {/* ── Certificate Detail Drawer ── */}
      <Drawer
        title={
          <Space>
            <ClockCircleOutlined style={{ color: T.warning }} />
            <span>即将到期证书</span>
            <Tag
              style={{
                color: T.warning, backgroundColor: T.peach, border: 'none',
                borderRadius: 6, fontSize: 12, fontWeight: 600,
              }}
            >
              {data.expiringCerts.length} 张
            </Tag>
          </Space>
        }
        placement="right"
        size="large"
        open={certDrawerOpen}
        onClose={() => setCertDrawerOpen(false)}
        styles={{ body: { padding: '12px 24px' } }}
      >
        {data.expiringCerts.length === 0 ? (
          <div className="text-center py-12">
            <CheckCircleOutlined style={{ fontSize: 40, color: T.muted }} />
            <Text className="block mt-3" style={{ color: T.muted }}>
              暂无即将到期的证书
            </Text>
          </div>
        ) : (
          <Table<TrainingRecord>
            columns={certColumns}
            dataSource={data.expiringCerts}
            rowKey="id"
            size="middle"
            pagination={false}
            style={{ borderRadius: 8 }}
          />
        )}
      </Drawer>

      {/* ── 未关闭隐患明细抽屉（来源可切换） ── */}
      <Drawer
        title={
          <Space>
            <WarningOutlined style={{ color: T.warning }} />
            <span>
              未关闭隐患 · {HAZARD_SOURCE_META_LABEL(hazardSource)}
            </span>
            <Tag
              style={{
                color: T.warning, backgroundColor: T.peach, border: 'none',
                borderRadius: 6, fontSize: 12, fontWeight: 600,
              }}
            >
              {openHazardCount} 条
            </Tag>
          </Space>
        }
        placement="right"
        size="large"
        open={hazardDrawerOpen}
        onClose={() => setHazardDrawerOpen(false)}
      >
        <Segmented
          size="small"
          value={hazardSource}
          onChange={(v) => {
            const next = v as 'duty' | 'ledger'
            setHazardSource(next)
            void loadOpenHazards(next)
          }}
          options={[
            { label: '24小时隐患', value: 'duty' },
            { label: '隐患台账', value: 'ledger' },
          ]}
          className="mb-3"
        />
        {hazardLoading ? (
          <Text style={{ color: T.muted }}>加载中…</Text>
        ) : openHazardRows.length === 0 ? (
          <div className="text-center py-10">
            <CheckCircleOutlined style={{ fontSize: 36, color: T.mint }} />
            <Text className="block mt-2" style={{ color: T.muted }}>
              该来源暂无未关闭隐患
            </Text>
          </div>
        ) : (
          <div className="space-y-2">
            {openHazardRows.map((row) => (
              <div
                key={row.record_id}
                className="rounded-lg p-3"
                style={{ backgroundColor: T.surface, borderRadius: 8 }}
              >
                <Text
                  className="block text-sm"
                  style={{ color: T.charcoal }}
                  title={row.content}
                >
                  {row.content || '（无内容描述）'}
                </Text>
                <div
                  className="flex items-center gap-3 mt-1 flex-wrap"
                  style={{ fontSize: 11 }}
                >
                  {row.where && (
                    <Text style={{ color: T.steel }}>
                      <EnvironmentOutlined /> {row.where}
                    </Text>
                  )}
                  {row.who && (
                    <Text style={{ color: T.steel }}>
                      <UserOutlined /> {row.who}
                    </Text>
                  )}
                  {row.date && (
                    <Text style={{ color: T.steel }}>{row.date}</Text>
                  )}
                  {row.status && (
                    <Tag
                      style={{
                        color: T.warning, backgroundColor: T.peach, border: 'none',
                        borderRadius: 6, fontSize: 10, fontWeight: 600, margin: 0,
                      }}
                    >
                      {row.status}
                    </Tag>
                  )}
                </div>
              </div>
            ))}
            {openHazardRows.length >= 50 && (
              <Text style={{ color: T.muted, fontSize: 11 }}>
                仅显示最近 50 条，更多请前往对应台账页面查看
              </Text>
            )}
          </div>
        )}
      </Drawer>

      {/* ── 危险源辨识未完成明细抽屉 ── */}
      <Drawer
        title={
          <Space>
            <RobotOutlined style={{ color: T.primary }} />
            <span>危险源辨识未完成明细</span>
            <Tag
              style={{
                color: T.primary, backgroundColor: T.lavender, border: 'none',
                borderRadius: 6, fontSize: 12, fontWeight: 600,
              }}
            >
              {unfinishedIdents.length} 条
            </Tag>
          </Space>
        }
        placement="right"
        size="large"
        open={identDrawerOpen}
        onClose={() => setIdentDrawerOpen(false)}
      >
        {unfinishedIdents.length === 0 ? (
          <div className="text-center py-10">
            <CheckCircleOutlined style={{ fontSize: 36, color: T.mint }} />
            <Text className="block mt-2" style={{ color: T.muted }}>
              暂无未完成的危险源辨识
            </Text>
          </div>
        ) : (
          <div className="space-y-2">
            {unfinishedIdents.map((item) => (
              <div
                key={item.id}
                className="rounded-lg p-3 cursor-pointer transition-colors hover:bg-[var(--color-surface)]"
                style={{ backgroundColor: T.surface, borderRadius: 8 }}
                onClick={() => router.push('/safety/hazard-identification')}
              >
                <Text className="block text-sm" style={{ color: T.charcoal }}>
                  {item.hazard_id_no || '（未编号）'}
                </Text>
                <div
                  className="flex items-center gap-3 mt-1"
                  style={{ fontSize: 11 }}
                >
                  <Text style={{ color: T.steel }}>{item.department || '-'}</Text>
                  <Tag
                    style={{
                      color: T.primary, backgroundColor: T.lavender, border: 'none',
                      borderRadius: 6, fontSize: 10, fontWeight: 600, margin: 0,
                    }}
                  >
                    {item.statusLabel}
                  </Tag>
                </div>
              </div>
            ))}
          </div>
        )}
      </Drawer>
    </div>
  )
}
