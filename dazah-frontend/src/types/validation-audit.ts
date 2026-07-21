// validation-audit module TypeScript types

// ── 枚举 ──────────────────────────────────────────────────

export type AuditMode = 'protocol' | 'report' | 'protocol_report'

export type TaskStatus = 'draft' | 'uploaded' | 'parsing' | 'auditing' | 'completed' | 'failed'

export type TaskConclusion = 'pass' | 'conditional_pass' | 'fail'

export type FileType = 'protocol' | 'report' | 'attachment'

export type ParseStatus = 'pending' | 'parsing' | 'completed' | 'failed'

export type IssueType = 'serious' | 'general' | 'suggestion'

// ── Task ──────────────────────────────────────────────────

export interface ValidationAuditTask {
  id: string
  task_name: string
  product_name: string
  method_name: string
  source_company: string
  audit_mode: AuditMode
  status: TaskStatus
  conclusion: TaskConclusion | null
  risk_level: string | null
  serious_count: number
  general_count: number
  suggestion_count: number
  compliant_count: number
  non_compliant_count: number
  report_path: string | null
  created_at: string
  updated_at: string
}

export interface ValidationAuditTaskListItem {
  id: string
  task_name: string
  product_name: string
  source_company: string
  audit_mode: AuditMode
  status: TaskStatus
  conclusion: TaskConclusion | null
  serious_count: number
  general_count: number
  suggestion_count: number
  created_at: string
}

export interface ValidationAuditTaskCreate {
  task_name: string
  product_name: string
  method_name: string
  source_company: string
  audit_mode: AuditMode
}

export interface ValidationAuditTaskUpdate {
  task_name?: string
  product_name?: string
  method_name?: string
  source_company?: string
  audit_mode?: AuditMode
}

export interface ValidationAuditTaskListResponse {
  code: number
  message: string
  data: {
    items: ValidationAuditTaskListItem[]
    total: number
  }
  meta?: {
    page: number
    page_size: number
    total: number
  }
}

export interface ValidationAuditTaskResponse {
  code: number
  message: string
  data: ValidationAuditTask
}

export interface ValidationAuditTaskListParams {
  product_name?: string
  source_company?: string
  status?: string
  page?: number
  page_size?: number
}

// ── File ──────────────────────────────────────────────────

export interface ValidationAuditFile {
  id: string
  task_id: string
  file_type: FileType
  original_filename: string
  file_path: string
  file_size: number
  parse_status: ParseStatus
  created_at: string
}

export interface ValidationAuditFileListItem {
  id: string
  file_type: FileType
  original_filename: string
  file_size: number
  parse_status: ParseStatus
  created_at: string
}

// ── Issue ─────────────────────────────────────────────────

export interface ValidationAuditIssue {
  id: string
  task_id: string
  file_id: string | null
  issue_no: string
  dimension: string
  check_item: string
  description: string
  suggestion: string | null
  issue_type: IssueType
  page_no: number | null
  evidence_text: string | null
  created_at: string
}

// ── Report ────────────────────────────────────────────────

export interface ValidationAuditReport {
  id: string
  task_id: string
  report_title: string
  report_markdown: string | null
  report_file_path: string | null
  version: number
  created_at: string
}

// ── 显示映射 ──────────────────────────────────────────────

export const AUDIT_MODE_LABELS: Record<AuditMode, string> = {
  protocol: '方案审核',
  report: '报告审核',
  protocol_report: '方案+报告联合审核',
}

export const STATUS_LABELS: Record<TaskStatus, { label: string; color: string }> = {
  draft: { label: '草稿', color: 'default' },
  uploaded: { label: '已上传', color: 'blue' },
  parsing: { label: '解析中', color: 'processing' },
  auditing: { label: '审核中', color: 'processing' },
  completed: { label: '已完成', color: 'success' },
  failed: { label: '失败', color: 'error' },
}

export const CONCLUSION_LABELS: Record<TaskConclusion, { label: string; color: string }> = {
  pass: { label: '通过', color: 'success' },
  conditional_pass: { label: '有条件通过', color: 'warning' },
  fail: { label: '不通过', color: 'error' },
}

export const ISSUE_TYPE_LABELS: Record<IssueType, { label: string; color: string }> = {
  serious: { label: '严重问题', color: 'error' },
  general: { label: '一般问题', color: 'warning' },
  suggestion: { label: '建议优化', color: 'blue' },
}

export const PARSE_STATUS_LABELS: Record<ParseStatus, { label: string; color: string }> = {
  pending: { label: '待解析', color: 'default' },
  parsing: { label: '解析中', color: 'processing' },
  completed: { label: '已解析', color: 'success' },
  failed: { label: '解析失败', color: 'error' },
}
