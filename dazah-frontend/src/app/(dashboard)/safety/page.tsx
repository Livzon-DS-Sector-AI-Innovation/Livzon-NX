import {
  getHazards,
  getHazardIdentifications,
  getExpiringCertificates,
  getSpecialOperationReports,
  getDailyRiskReports,
  getSafetyOverview,
  getChemicalInventories,
  getSafetyPageTableStats,
  getSafetyPageTableRecords,
} from '@/actions/safety'
import { SafetyDashboard } from '@/components/safety'
import type { SpecialOperationReport, DailyRiskReport, TrainingRecord } from '@/types/safety'

export const dynamic = 'force-dynamic'
export const revalidate = 60

// 未关闭隐患 KPI 的默认数据源：24小时值班隐患（飞书镜像表），
// 用户可在卡片上切换为「隐患台账」
const HAZARD_DUTY_KEY = 'safety:risk-hazard:hazard-inspection:hazard-duty'
const HAZARD_DUTY_STATUS_FIELD = '整改情况'
const HAZARD_DUTY_CLOSED_VALUE = '已整改'

function isToday(dateStr?: string): boolean {
  if (!dateStr) return false
  const today = new Date()
  const d = new Date(dateStr)
  return (
    d.getFullYear() === today.getFullYear() &&
    d.getMonth() === today.getMonth() &&
    d.getDate() === today.getDate()
  )
}

// 驾驶舱口径与后端 overview 一致：驳回/草稿的作业未实际发生，不计入当日
const COCKPIT_EXCLUDED_STATUSES = new Set(['draft', 'rejected'])

function isCockpitVisible(status?: string): boolean {
  return !status || !COCKPIT_EXCLUDED_STATUSES.has(status)
}

async function fetchDashboardData() {
  const now = new Date()
  const todayStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`

  const [
    hazardsRes,
    identificationsRes,
    expiringCertsRes,
    specialOpReportsRes,
    dailyRiskReportsRes,
    overviewRes,
    inventoriesRes,
    dutyStatsRes,
    dutyRecordsRes,
  ] = await Promise.all([
    getHazards({ page_size: 200 }),
    getHazardIdentifications({ page_size: 200 }),
    getExpiringCertificates().catch(() => ({ data: [] })),
    getSpecialOperationReports({ page_size: 50 }).catch(() => ({ data: [], meta: { total: 0 } })),
    getDailyRiskReports({ page_size: 50, report_date: todayStr }).catch(() => ({ data: [], meta: { total: 0 } })),
    getSafetyOverview().catch(() => null),
    getChemicalInventories({ page_size: 200 }).catch(() => null),
    // 未关闭隐患（默认来源：24小时值班隐患）：统计未整改数量并取未整改明细
    getSafetyPageTableStats({
      pageKey: HAZARD_DUTY_KEY,
      groupBy: [HAZARD_DUTY_STATUS_FIELD],
      conditions: [
        {
          field: HAZARD_DUTY_STATUS_FIELD,
          op: 'neq',
          value: HAZARD_DUTY_CLOSED_VALUE,
        },
      ],
    }).catch(() => null),
    getSafetyPageTableRecords({
      pageKey: HAZARD_DUTY_KEY,
      pageSize: 50,
      conditions: [
        {
          field: HAZARD_DUTY_STATUS_FIELD,
          op: 'neq',
          value: HAZARD_DUTY_CLOSED_VALUE,
        },
      ],
    }).catch(() => null),
  ])

  // 未关闭隐患：过滤 status != closed && != verified
  const hazardsAll = Array.isArray((hazardsRes as { data?: unknown[] }).data)
    ? (hazardsRes as { data: { status: string }[] }).data
    : []

  // 未关闭隐患（24小时值班隐患口径）：统计接口 neq 条件已排除已整改，
  // total 即未关闭数量；同时取未整改明细供卡片抽屉展示
  const dutyStatsData =
    dutyStatsRes && dutyStatsRes.code === 200 && dutyStatsRes.data
      ? dutyStatsRes.data
      : null
  const dutyRecordsData =
    dutyRecordsRes && dutyRecordsRes.code === 200 && dutyRecordsRes.data
      ? dutyRecordsRes.data
      : null
  const openHazardCount = dutyStatsData?.total ?? 0
  const openHazardRecords = (dutyRecordsData?.records ?? []).map(
    (row: { record_id: string; fields?: Record<string, unknown> | null }) => ({
      record_id: row.record_id,
      fields: row.fields ?? {},
    })
  )

  // 未完成危险源辨识：过滤 overall_status = draft 或 in_progress
  const identificationsAll = Array.isArray((identificationsRes as { data?: unknown[] }).data)
    ? (identificationsRes as {
        data: {
          id: string
          hazard_id_no: string
          department: string
          overall_status: string
        }[]
      }).data
    : []
  const unfinishedIdentCount = identificationsAll.filter(
    (i) => i.overall_status === 'draft' || i.overall_status === 'in_progress'
  ).length

  // 即将到期证书
  const expiringCerts = (Array.isArray(expiringCertsRes?.data) ? expiringCertsRes.data : []) as TrainingRecord[]

  // 当天特殊作业报备（排除驳回/草稿，与驾驶舱地图口径一致）
  const specialOpReports = (Array.isArray((specialOpReportsRes as { data?: SpecialOperationReport[] }).data)
    ? (specialOpReportsRes as { data: SpecialOperationReport[] }).data
    : []) as SpecialOperationReport[]
  const todaySpecialOps = specialOpReports.filter(
    (r) => isToday(r.planned_start_time) && isCockpitVisible(r.status)
  )

  // 每日风险作业报备（同样排除驳回/草稿）
  const dailyRiskReports = (Array.isArray((dailyRiskReportsRes as { data?: DailyRiskReport[] }).data)
    ? (dailyRiskReportsRes as { data: DailyRiskReport[] }).data
    : []) as DailyRiskReport[]
  const todayDailyRisks = dailyRiskReports.filter(
    (r) => isToday(r.report_date) && isCockpitVisible(r.status)
  )

  return {
    openHazardCount,
    openHazardRecords,
    unfinishedIdentCount,
    expiringCerts,
    todaySpecialOps,
    todayDailyRisks,
    overview: overviewRes && 'data' in overviewRes ? overviewRes.data : null,
    // 危化品车间存量（驾驶舱“危化品每日统计”卡片数据源）
    chemicalInventories:
      inventoriesRes && inventoriesRes.code === 200 && inventoriesRes.data
        ? inventoriesRes.data.items
        : [],

    unfinishedIdentifications: identificationsAll
      .filter(
        (i) => i.overall_status === 'draft' || i.overall_status === 'in_progress'
      )
      .map((i) => ({
        id: String(i.id),
        hazard_id_no: String(i.hazard_id_no ?? ''),
        department: String(i.department ?? ''),
        overall_status: String(i.overall_status ?? ''),
      })),
  }
}

export default async function SafetyPage() {
  const data = await fetchDashboardData()

  return <SafetyDashboard data={data} />
}
