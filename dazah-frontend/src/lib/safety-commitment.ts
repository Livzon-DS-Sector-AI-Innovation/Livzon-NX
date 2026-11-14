/**
 * 安全承诺页（应急〔2018〕74号 承诺公告制度）共享常量与类型。
 */

export const SAFETY_COMMITMENT_PAGE_KEY = 'safety:safety-commitment'

/** 企业状态结构化数据（与后端 default_enterprise_status 对齐） */
export type EnterpriseStatus = {
  workshop_total: number
  workshop_running: number
  workshop_stopped: number
  workshop_maintenance: number
  trial_production_count: number
  startup_count: number
  shutdown_count: number
  special_work_total: number
  special_work: {
    hot_work_level1: number
    hot_work_level2: number
    height_work: number
    confined_space: number
    other: number
  }
  hazard_count: number
  hazard_rectified?: boolean | null
  hazard_temp_measures?: boolean | null
  contractor_work?: boolean
  contractor_trained?: boolean | null
  major_hazard_safe?: boolean | null
  responsibility_implemented?: boolean | null
  person_main?: string
  person_tech?: string
  person_ops?: string
}

export type RiskAssessment = {
  risk_level: string
  summary: string
  key_risks: string[]
  suggestions: string[]
  data_basis?: Record<string, number>
  generated_at?: string
  edited?: boolean
}

export type SafetyCommitmentReport = {
  id: string
  report_date: string
  enterprise_status: Partial<EnterpriseStatus>
  commitment_text?: string | null
  risk_assessment?: RiskAssessment | null
  status: 'draft' | 'published'
  publisher_name?: string | null
  published_at?: string | null
  fill_source?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export type CommitmentCardType = 'commitment' | 'major_hazard'

export type SafetyCommitmentCard = {
  id: string
  card_type: CommitmentCardType
  title: string
  content: string
  sort_order: number
  updated_at?: string | null
}

export function defaultEnterpriseStatus(): EnterpriseStatus {
  return {
    workshop_total: 0,
    workshop_running: 0,
    workshop_stopped: 0,
    workshop_maintenance: 0,
    trial_production_count: 0,
    startup_count: 0,
    shutdown_count: 0,
    special_work_total: 0,
    special_work: {
      hot_work_level1: 0,
      hot_work_level2: 0,
      height_work: 0,
      confined_space: 0,
      other: 0,
    },
    hazard_count: 0,
    hazard_rectified: null,
    hazard_temp_measures: null,
    contractor_work: false,
    contractor_trained: null,
    major_hazard_safe: null,
    responsibility_implemented: null,
    person_main: '',
    person_tech: '',
    person_ops: '',
  }
}

/** 今日日期（北京时间 YYYY-MM-DD；与后端日报自然日口径一致）。
 *
 * 必须用固定时区而非本地时间：SSR（Node 容器 UTC）与浏览器本地时区
 * 可能不同，`new Date()` 会导致水合前后日期不一致。
 */
export function todayStr(): string {
  // en-CA 输出恰好是 YYYY-MM-DD
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date())
}

const CN_DATETIME = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

/** 时间戳按北京时间格式化（SSR 与浏览器结果一致，避免水合不一致）。 */
export function formatCnDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return '—'
  return CN_DATETIME.format(parsed)
}

export type WorkshopConfig = {
  id: string
  workshop_name: string
  reporter_open_id: string
  reporter_name: string
  sort_order: number
  is_enabled: boolean
}

export type WorkshopFillRow = {
  workshop_name: string
  reporter_name: string
  reporter_open_id: string
  filled: boolean
  filled_by_name: string
  filled_at: string | null
  fields: Partial<EnterpriseStatus>
  remark: string
  source: string
}

export type WorkshopFillsProgress = {
  report_date: string
  total: number
  filled: number
  workshops: WorkshopFillRow[]
}
