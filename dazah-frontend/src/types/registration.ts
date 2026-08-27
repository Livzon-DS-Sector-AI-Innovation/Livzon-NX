// registration module TypeScript types
//
// NOTE: API 输入类型（Create/Update）从 @/types/generated/schema 导入（见下方）。
// API 响应类型也由 @/types/generated/schema 导入，与后端 OpenAPI spec 自动同步。
// 仅有少数辅助类型（AuthorizationLedgerOverview）以及两个 Form 参数类型
// （AuthorizationLetterCreateInput、AuthorizationLedgerEntryInput）仍手写，
// 因为后端未在 OpenAPI spec 中导出这些 schema。
//
// 后端 Pydantic 模型中部分本应必填的数组/对象字段被标记为 Optional，
// 导致 OpenAPI spec 中这些字段带 `?`。前端既有代码假定它们始终存在，
// 因此对受影响的响应类型使用 `Required<...>` 去掉可选标记；对包含嵌套
// 响应类型引用的字段，使用 `Omit<Required<...>, 'field'> & { field: Alias }`
// 将嵌套类型替换为本文件中的别名，确保嵌套结构也同步去可选化。
//
// 后端 OpenAPI 变更后，运行 `pnpm generate:api` 重新生成 schema.ts 即可自动同步。

import type { components } from '@/types/generated/schema'

// ── Input types from generated schema ────────────────────────────────────

export type AuthorizationFdaEntryInput = components['schemas']['AuthorizationFdaEntryCreate']
export type AuthorizationFdaEntryUpdateInput = components['schemas']['AuthorizationFdaEntryUpdate']
export type AuthorizationLedgerMainCreateInput = components['schemas']['AuthorizationLedgerMainCreate']
export type AuthorizationLedgerMainUpdateInput = components['schemas']['AuthorizationLedgerMainUpdate']
export type AuthorizationLedgerUpdateCreateInput = components['schemas']['AuthorizationLedgerUpdateCreate']
export type AuthorizationLedgerUpdateUpdateInput = components['schemas']['AuthorizationLedgerUpdateUpdate']
export type CertificateEntryInput = components['schemas']['CertificateEntryCreate']
export type CertificateReminderSettingInput = components['schemas']['CertificateReminderSettingUpdate']
export type DeclarationProgressEntryInput = components['schemas']['DeclarationProgressEntryInput']
export type FeeEntryCreateInput = components['schemas']['FeeEntryCreate']
export type FeeEntryUpdateInput = components['schemas']['FeeEntryUpdate']
export type InspectionContactCreateInput = components['schemas']['InspectionContactCreate']
export type InspectionContactUpdateInput = components['schemas']['InspectionContactUpdate']
export type KnowledgeArticleCreateInput = components['schemas']['KnowledgeArticleCreate']
export type KnowledgeArticleUpdateInput = components['schemas']['KnowledgeArticleUpdate']
export type KnowledgeCategoryCreateInput = components['schemas']['KnowledgeCategoryCreate']
export type KnowledgeCategoryUpdateInput = components['schemas']['KnowledgeCategoryUpdate']
export type KnowledgeCommentCreateInput = components['schemas']['KnowledgeCommentCreate']
export type KnowledgeCommentUpdateInput = components['schemas']['KnowledgeCommentUpdate']
export type ProjectLedgerEntryInput = components['schemas']['ProjectLedgerEntryInput']

// Backward-compatible aliases (deprecated, use *Input types above)
export type FeeEntryCreate = FeeEntryCreateInput
export type FeeEntryUpdate = FeeEntryUpdateInput
export type InspectionContactCreate = InspectionContactCreateInput
export type InspectionContactUpdate = InspectionContactUpdateInput
export type KnowledgeArticleCreate = KnowledgeArticleCreateInput
export type KnowledgeArticleUpdate = KnowledgeArticleUpdateInput
export type KnowledgeCategoryCreate = KnowledgeCategoryCreateInput
export type KnowledgeCategoryUpdate = KnowledgeCategoryUpdateInput
export type KnowledgeCommentCreate = KnowledgeCommentCreateInput
export type KnowledgeCommentUpdate = KnowledgeCommentUpdateInput

// AuthorizationLetterCreateInput - backend uses Form parameters, not exported to OpenAPI
export interface AuthorizationLetterCreateInput {
  product_name: string
  registration_number: string
  preparation_unit: string
  preparation_name: string
  administration_route: string
  remarks?: string | null
}

// AuthorizationLedgerEntryInput - legacy type used in frontend forms
// Backend uses AuthorizationLedgerMainCreate + AuthorizationLedgerUpdateCreate
export interface AuthorizationLedgerEntryInput {
  product_name: string
  market_name?: string | null
  source_sequence?: string | null
  authorization_file_name: string
  quality_standard?: string | null
  company_name?: string | null
  country?: string | null
  customer_code?: string | null
  purpose?: string | null
  authorization_date?: string | null
  handler?: string | null
  status?: string | null
  remarks?: string | null
}

// ── Response types from generated schema ─────────────────────────────────
// 与后端 OpenAPI spec 自动同步。对后端标记为 Optional 但前端按必填使用的
// 字段，使用 Required<...> 去可选；对嵌套响应类型引用使用 Omit + 交集替换
// 为本文件中的别名，确保嵌套层级也保持一致。

// ── Authorization response types ─────────────────────────────────────────

export type ProductInfo = components['schemas']['ProductInfo']
export type AuthorizationOverview = components['schemas']['AuthorizationOverview']
export type AuthorizationFdaRecord = components['schemas']['AuthorizationFdaRecord']
export type AuthorizationLedgerUpdateRecord = components['schemas']['AuthorizationLedgerUpdateRead']
// AuthorizationLedgerRecord 对应后端 AuthorizationLedgerMainRead；
// 使用 Required 确保 updates 字段按必填使用（前端既有逻辑依赖其存在）。
export type AuthorizationLedgerRecord = Required<components['schemas']['AuthorizationLedgerMainRead']>
export type AuthorizationProductDetail = components['schemas']['AuthorizationProductDetail']
export type AuthorizationLetter = components['schemas']['AuthorizationLetterResponse']

// AuthorizationLedgerOverview 后端未在 OpenAPI spec 中导出，暂时手写
// TODO: 后端补全 OpenAPI 响应 schema 后，运行 `pnpm generate:api` 重新生成并替换为引用

export interface AuthorizationLedgerOverview {
  total_main_records: number
  total_update_records: number
  total_products: number
  total_markets: number
  submitted_main_records: number
  pending_main_records: number
}

// ── Certificate types ────────────────────────────────────────────────────

export type CertificateRecordSummary = components['schemas']['CertificateRecordSummary']
export type CertificateSheetSummary = components['schemas']['CertificateSheetSummary']
export type CertificateColumn = components['schemas']['CertificateColumn']
export type CertificateSheetRow = Required<components['schemas']['CertificateSheetRow']>
// CertificateSheetDetail.rows 需引用本文件中的 CertificateSheetRow 别名，
// 以确保 rows[number].values 按必填使用。
export type CertificateSheetDetail = Omit<
  Required<components['schemas']['CertificateSheetDetail']>,
  'rows'
> & {
  rows: CertificateSheetRow[]
}
export type CertificateWorkbookSheet = components['schemas']['CertificateWorkbookSheet']
export type CertificateWorkbookOverview = Required<components['schemas']['CertificateWorkbookOverview']>
export type CertificateWorkbookDetail = components['schemas']['CertificateWorkbookDetail']
export type CertificateWorkbookImportResult = components['schemas']['CertificateWorkbookImportResult']
export type CertificateReminderRecipientOption = components['schemas']['CertificateReminderRecipientOption']
export type CertificateReminderSetting = components['schemas']['CertificateReminderSettingResponse']

// ── Project types ────────────────────────────────────────────────────────

export type ProjectLedgerColumn = components['schemas']['ProjectLedgerColumn']
export type ProjectLedgerHistoryRecord = Required<components['schemas']['ProjectLedgerHistoryRecord']>
// ProjectLedgerRecord.latest_values 与 history_records 在前端按必填使用；
// history_records 元素引用本文件中的 ProjectLedgerHistoryRecord 别名。
export type ProjectLedgerRecord = Required<components['schemas']['ProjectLedgerRecord']>
export type ProjectLedgerRecordHistory = Omit<
  Required<components['schemas']['ProjectLedgerRecordHistory']>,
  'history_records'
> & {
  history_records: ProjectLedgerHistoryRecord[]
}
export type ProjectLedgerSheetSummary = components['schemas']['ProjectLedgerSheetSummary']
// ProjectLedgerSheetDetail.records 需引用本文件中的 ProjectLedgerRecord 别名。
export type ProjectLedgerSheetDetail = Omit<
  Required<components['schemas']['ProjectLedgerSheetDetail']>,
  'records'
> & {
  records: ProjectLedgerRecord[]
}
// ProjectLedgerWorkbookOverview.sheets 需引用本文件中的 ProjectLedgerSheetDetail 别名。
export type ProjectLedgerWorkbookOverview = Omit<
  Required<components['schemas']['ProjectLedgerWorkbookOverview']>,
  'sheets'
> & {
  sheets: ProjectLedgerSheetDetail[]
}
export type ProjectLedgerWorkbookImportResult = components['schemas']['ProjectLedgerWorkbookImportResult']
export type ProjectChildPage = components['schemas']['ProjectChildPage']
export type ProjectApiEndpoint = components['schemas']['ProjectApiEndpoint']
export type ProjectModuleOverviewItem = Required<components['schemas']['ProjectModuleOverviewItem']>
// ProjectOverview.modules 需引用本文件中的 ProjectModuleOverviewItem 别名。
export type ProjectOverview = Omit<
  Required<components['schemas']['ProjectOverview']>,
  'modules'
> & {
  modules: ProjectModuleOverviewItem[]
}

// ── Declaration progress types ───────────────────────────────────────────

export type DeclarationProgressColumn = components['schemas']['DeclarationProgressColumn']
export type DeclarationProgressHistoryRecord = Required<components['schemas']['DeclarationProgressHistoryRecord']>
// DeclarationProgressRecord.latest_values / latest_style_marks / history_records
// 在前端按必填使用；history_records 元素引用本文件中的 DeclarationProgressHistoryRecord 别名。
export type DeclarationProgressRecord = Required<components['schemas']['DeclarationProgressRecord']>
export type DeclarationProgressRecordHistory = Omit<
  Required<components['schemas']['DeclarationProgressRecordHistory']>,
  'history_records'
> & {
  history_records: DeclarationProgressHistoryRecord[]
}
export type DeclarationProgressSheetSummary = components['schemas']['DeclarationProgressSheetSummary']
// DeclarationProgressSheetDetail.records 需引用本文件中的 DeclarationProgressRecord 别名。
export type DeclarationProgressSheetDetail = Omit<
  Required<components['schemas']['DeclarationProgressSheetDetail']>,
  'records'
> & {
  records: DeclarationProgressRecord[]
}
// DeclarationProgressWorkbookOverview.sheets 需引用本文件中的 DeclarationProgressSheetDetail 别名。
export type DeclarationProgressWorkbookOverview = Omit<
  Required<components['schemas']['DeclarationProgressWorkbookOverview']>,
  'sheets'
> & {
  sheets: DeclarationProgressSheetDetail[]
}
export type DeclarationProgressWorkbookImportResult = components['schemas']['DeclarationProgressWorkbookImportResult']

// ── Fee types ────────────────────────────────────────────────────────────

export type FeeEntry = components['schemas']['FeeEntryResponse']
export type InspectionContact = components['schemas']['InspectionContactResponse']
export type FeeTypeSummary = components['schemas']['FeeTypeSummary']
export type PaymentStatusSummary = components['schemas']['PaymentStatusSummary']
export type YearSummary = components['schemas']['YearSummary']
export type YearFeeTypeSummary = components['schemas']['YearFeeTypeSummary']
export type FeeOverview = components['schemas']['FeeOverview']
export type AgencySummary = components['schemas']['AgencySummary']
// FeeDashboardResponse 中各汇总数组在后端被标记为 Optional，前端按必填使用。
export type FeeDashboard = Required<components['schemas']['FeeDashboardResponse']>

// ── Knowledge types ──────────────────────────────────────────────────────

export type KnowledgeCategory = components['schemas']['KnowledgeCategoryResponse']
export type KnowledgeArticle = components['schemas']['KnowledgeArticleResponse']
export type KnowledgeArticleListItem = components['schemas']['KnowledgeArticleListItem']
export type KnowledgeOverview = components['schemas']['KnowledgeOverview']

// ── Attachment types ─────────────────────────────────────────────────────

export type KnowledgeAttachment = components['schemas']['KnowledgeAttachmentResponse']

// ── Comment types ────────────────────────────────────────────────────────

export type KnowledgeComment = components['schemas']['KnowledgeCommentResponse']

// ── Article detail with attachments and comments ─────────────────────────
// attachments / comments 在后端被标记为 Optional，前端按必填使用。

export type KnowledgeArticleDetail = Required<components['schemas']['KnowledgeArticleDetail']>
export interface ReferenceStandardListItem {
  id: string
  drug_name: string
  reference_substance_name?: string | null
  batch_number?: string | null
  manufacturer?: string | null
  output_file_name: string
  created_at?: string | null
}

export interface SupplementaryReplyListItem {
  id: string
  drug_name?: string | null
  registration_number?: string | null
  acceptance_number?: string | null
  company_name?: string | null
  question_count?: number | null
  output_file_name?: string | null
  created_at: string
  updated_at?: string | null
}
