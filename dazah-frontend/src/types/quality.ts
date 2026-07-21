// Quality management types (from shared/api.interface.ts)

// ============ Deviation Types ============
export type DeviationLevel = 'minor' | 'moderate' | 'major';
export type DeviationStatus =
  | 'draft'
  | 'pending_ai_analysis'
  | 'pending_investigation'
  | 'pending_dept_head_review'
  | 'pending_cross_dept_head_review'
  | 'pending_qa_review'
  | 'pending_qa_head_review'
  | 'pending_quality_head_review'
  | 'pending_final_code'
  | 'returned'
  | 'closed'
  | 'cancelled';

export type ApprovalStep =
  | 'ai_analysis'
  | 'investigation'
  | 'dept_head_review'
  | 'cross_dept_head_review'
  | 'qa_review'
  | 'qa_head_review'
  | 'quality_head_review'
  | 'final_code_input';

export type ReasonCategory = '人员' | '设施/设备' | '产品/物料' | '文件' | '环境' | '其它';

export interface QualityAiStructuredFields extends Record<string, unknown> {
  match_rule?: string;
  has_linked_deviation?: boolean;
  deviation_code?: string;
  source_code?: string;
}

export interface QualityAiInputSnapshot extends Record<string, unknown> {
  analysis_context?: QualityAiStructuredFields;
  linked_deviation?: { deviation_code?: string };
  capa?: { source_code?: string };
}

export interface CrossDeptReviewer {
  department: string;
  investigators: string[];
}

export interface AiAnalysis {
  structured_deviation_description?: string | null;
  preliminary_cause_analysis?: string | null;
  risk_assessment?: string | null;
  capa_suggestions?: string | null;
  summary?: string | null;
  risk_level?: string | null;
  risks?: string[];
  suggestions?: string[];
  missing_info?: string[];
  structured_fields?: QualityAiStructuredFields;
  disclaimer?: string | null;
}

export interface InvestigationRecord {
  content?: string;
  nonconformityDescription?: string;
  rootCauseAnalysis?: string;
  riskAssessment?: string;
  urgentMeasures?: string;
  author: string;
  department?: string;
  createTime: string;
  attachments?: string[];
  isModified?: boolean;
  modifyTime?: string;
  capaProposals?: Array<Record<string, unknown>>;
}

export interface ReviewOpinion {
  content: string;
  author: string;
  step: ApprovalStep | string;
  result: 'approved' | 'rejected' | 'resubmitted';
  createTime: string;
}

export interface DeviationListItem {
  id: string;
  deviation_code: string;
  final_code: string | null;
  title: string;
  department: string | null;
  discovery_date: string | null;
  discovery_time?: string | null;
  status: DeviationStatus;
  level: DeviationLevel | null;
  root_cause_category: ReasonCategory | null;
  reporter_id: string | null;
  handler: string | null;
  batch_number: string | null;
  affected_items: string | null;
  description: string | null;
  has_occurred_before: boolean | null;
  material_disposition: string | null;
  corrective_actions: string | null;
  root_cause_analysis: string | null;
  investigation_completed_at: string | null;
  close_time?: string | null;
  related_capa_codes?: string[] | null;
  related_capas?: Array<{
    id: string;
    capa_code: string;
  }> | null;
  feishu_base_table_id?: string | null;
  feishu_base_record_id?: string | null;
  feishu_sync_status?: string | null;
  feishu_last_sync_error?: string | null;
  feishu_last_sync_direction?: 'system_to_base' | 'base_to_system' | string | null;
  feishu_synced_at?: string | null;
  feishu_source_updated_at?: string | null;
  status_updated_at: string | null;
  returned_step: ApprovalStep | null;
  created_at: string;
}

export interface FeishuPageRecordBase {
  id: string;
  record_id: string;
  source: 'feishu';
}

export interface FeishuDeviationReportRecordItem extends FeishuPageRecordBase {
  id: string;
  record_id: string;
  deviation_id?: string | null;
  deviation_code?: string | null;
  report_time?: string | null;
  description?: string | null;
  report_document?: string | null;
  product_batch?: string | null;
  product_name_batch?: string | null;
  department?: string | null;
  reporter_name?: string | null;
  department_head?: string | null;
  department_head_result?: string | null;
  department_head_reviewed_at?: string | null;
  qa_name?: string | null;
  qa_result?: string | null;
  qa_reviewed_at?: string | null;
  qa_head_name?: string | null;
  qa_head_result?: string | null;
  qa_head_reviewed_at?: string | null;
  report_status?: string | null;
  feishu_base_table_id?: string | null;
  feishu_base_record_id?: string | null;
  feishu_sync_status?: string | null;
  feishu_last_sync_error?: string | null;
  feishu_last_sync_direction?: 'system_to_base' | 'base_to_system' | string | null;
  feishu_synced_at?: string | null;
  feishu_source_updated_at?: string | null;
}

export type DeviationReportRecordItem = FeishuDeviationReportRecordItem;

export interface DeviationDetail {
  id: string;
  deviation_code: string;
  final_code: string | null;
  title: string;
  department: string | null;
  discovery_date: string | null;
  discovery_time: string | null;
  discovery_location: string | null;
  status: DeviationStatus;
  level: DeviationLevel | null;
  root_cause_category: ReasonCategory | null;
  description: string | null;
  immediate_actions: string | null;
  reporter_id: string | null;
  handler: string | null;
  discoverer: string | null;
  ai_analysis: AiAnalysis | null;
  investigation_records: InvestigationRecord[] | null;
  review_opinions: ReviewOpinion[] | null;
  attachments: string[] | null;
  needs_cross_dept_review: boolean | null;
  cross_dept_reviewers: CrossDeptReviewer[] | null;
  affected_items: string | null;
  batch_number: string | null;
  has_occurred_before?: boolean | null;
  material_disposition?: string | null;
  corrective_actions?: string | null;
  root_cause_analysis?: string | null;
  investigation_completed_at?: string | null;
  returned_step: ApprovalStep | null;
  status_updated_at: string | null;
  report_content: string | null;
  report_versions: ReportVersion[] | null;
  feishu_base_table_id?: string | null;
  feishu_base_record_id?: string | null;
  feishu_sync_status?: string | null;
  feishu_last_sync_error?: string | null;
  feishu_last_sync_direction?: 'system_to_base' | 'base_to_system' | string | null;
  feishu_synced_at?: string | null;
  feishu_source_updated_at?: string | null;
  created_at: string;
  updated_at: string;
}

// ============ Feishu Native Types ============
export interface FeishuCapaLedgerItem {
  record_id: string
  启动日期: string | null
  事件部门: string | null
  涉及产品: string | null
  CAPA简述: string | null
  CAPA效果评估: string | null
  关闭日期: string | null
  QA质量员: string | null
  QA质量员确认日期: string | null
  CAPA状态: string | null
  CAPA编号: string
}

export interface FeishuCapaPlanTrackItem {
  record_id: string
  CAPA编号: string
  计划内容: string | null
  完成时间: string | null
  责任人: string | null
  责任人确认: boolean
  部门负责人确认: boolean
  进度: string | null
  提醒状态: string | null
}

export interface FeishuListResponse<T> {
  items: T[]
  total: number
}

// ============ CAPA Types ============
export type CapaWorkflowStatus =
  | 'draft'
  | 'part_a'
  | 'part_b'
  | 'part_c'
  | 'pending_dept_head_confirm'
  | 'pending_qa_review'
  | 'pending_q_head_approval'
  | 'executing'
  | 'pending_evaluation'
  | 'submitted'
  | 'under_execution'
  | 'evaluation'
  | 'closed'
  | 'returned'
  | 'cancelled';

export type CapaSource = 'deviation' | 'audit' | 'customer_complaint' | 'internal_inspection';
export type CapaCategory = 'A' | 'B' | 'C';

export interface CapaItem {
  item_type: string;
  content: string;
  responsible_person?: string | null;
  deadline?: string | null;
  status: string;
}

export interface DeptHeadConfirmation {
  department: string;
  deptHeadUserId: string;
  result: string;
  opinion: string;
  confirmTime: string;
}

export interface ExecutionTrack {
  content: string;
  executor?: string | null;
  execution_date?: string | null;
  attachments?: string[] | null;
}

export interface CapaListItem {
  id: string;
  capa_code: string;
  final_code: string | null;
  title: string;
  status: CapaWorkflowStatus;
  source: string | null;
  source_code: string | null;
  category: CapaCategory | null;
  root_cause_category: ReasonCategory | null;
  deviation_id: string | null;
  department: string | null;
  affected_product: string | null;
  evaluation_result: string | null;
  closure_date: string | null;
  qa_confirmer: string | null;
  qa_confirm_date: string | null;
  expected_completion_date: string | null;
  linked_plan_contents?: string[] | null;
  linked_plan_tracks?: Array<{
    id: string;
    plan_content: string;
  }> | null;
  feishu_base_table_id?: string | null;
  feishu_base_record_id?: string | null;
  feishu_sync_status?: string | null;
  feishu_last_sync_error?: string | null;
  feishu_last_sync_direction?: 'system_to_base' | 'base_to_system' | string | null;
  feishu_synced_at?: string | null;
  feishu_source_updated_at?: string | null;
  status_updated_at: string | null;
  created_at: string;
}

export type RelatedCapaListItem = CapaListItem;

export interface CapaDetail {
  id: string;
  capa_code: string;
  final_code: string | null;
  title: string;
  status: CapaWorkflowStatus;
  deviation_id: string | null;
  source: string | null;
  source_code: string | null;
  category: CapaCategory | null;
  root_cause_category: ReasonCategory | null;
  non_conformity_description: string | null;
  root_cause_analysis: string | null;
  capa_content: string | null;
  capa_items: CapaItem[] | null;
  executors: string[] | null;
  expected_completion_date: string | null;
  qa_reviewer_id: string | null;
  qa_review_opinion: string | null;
  qa_review_time: string | null;
  q_head_approver_id: string | null;
  q_head_approval_opinion: string | null;
  q_head_approval_time: string | null;
  execution_status: string | null;
  execution_tracks: ExecutionTrack[] | null;
  dept_head_confirmations: DeptHeadConfirmation[] | null;
  evaluation_result: string | null;
  evaluation_target: string | null;
  evaluation_deadline: string | null;
  evaluation_confirmer_id: string | null;
  evaluation_confirm_date: string | null;
  closure_date: string | null;
  closure_remark: string | null;
  report_content: string | null;
  report_versions: ReportVersion[] | null;
  returned_step: string | null;
  status_updated_at: string | null;
  reporter: string | null;
  reason_category: string | null;
  feishu_base_table_id?: string | null;
  feishu_base_record_id?: string | null;
  feishu_sync_status?: string | null;
  feishu_last_sync_error?: string | null;
  feishu_last_sync_direction?: 'system_to_base' | 'base_to_system' | string | null;
  feishu_synced_at?: string | null;
  feishu_source_updated_at?: string | null;
  created_at: string;
  updated_at: string;
}

// ============ Change Types ============
export interface ChangeListItem {
  id: string;
  serial_number: string | null;
  change_code: string;
  applicant_department: string | null;
  change_object: string | null;
  change_content: string | null;
  impact_assessment: string | null;
  change_level: string | null;
  application_date: string | null;
  planned_approval_date: string | null;
  execution_date: string | null;
  closure_date: string | null;
  created_at: string;
  updated_at: string;
  action_plan_count: number;
}

export interface ChangeDetail extends ChangeListItem {
  created_by: string | null;
  updated_by: string | null;
}

export type ChangeActionPlanSyncStatus = 'pending' | 'synced' | 'failed';
export type ChangeActionPlanReminderStatus = 'pending' | 'reminded' | 'confirmed';

export interface ChangeActionPlanListItem {
  id: string;
  change_id: string | null;
  change_code: string;
  project_name: string;
  related_work: string | null;
  owner_name: string | null;
  owner_user_id: string | null;
  director_name: string | null;
  director_user_id: string | null;
  deadline_date: string | null;
  status: string | null;
  delay_flag: string | null;
  delayed_deadline_date: string | null;
  feishu_record_id: string | null;
  sync_status: ChangeActionPlanSyncStatus;
  sync_error: string | null;
  last_synced_at: string | null;
  reminder_enabled: boolean;
  reminder_status: ChangeActionPlanReminderStatus;
  last_reminded_at: string | null;
  reminder_confirmed_at: string | null;
  reminder_confirmed_by: string | null;
  reminder_message_id: string | null;
  created_at: string;
  updated_at: string;
}

export type ChangeActionPlanDetail = ChangeActionPlanListItem;

export interface ChangeActionPlanPersonOption {
  open_id: string;
  name: string;
  user_id: string | null;
  mobile: string | null;
  email: string | null;
  job_title: string | null;
}

export interface FeishuDeviationInvestigationPushRecordItem extends FeishuPageRecordBase {
  id: string;
  record_id: string;
  local_record_id?: string | null;
  deviation_id: string | null;
  deviation_code: string;
  push_round: string;
  investigation_report_url: string | null;
  submitted_at: string | null;
  submitter: string | null;
  department_head: string | null;
  department_head_result: string | null;
  department_head_reviewed_at: string | null;
  qa_name: string | null;
  qa_result: string | null;
  qa_reviewed_at: string | null;
  qa_head_name: string | null;
  qa_head_result: string | null;
  qa_head_reviewed_at: string | null;
  feishu_base_table_id?: string | null;
  feishu_base_record_id?: string | null;
  feishu_sync_status?: string | null;
  feishu_last_sync_error?: string | null;
  feishu_last_sync_direction?: 'system_to_base' | 'base_to_system' | string | null;
  feishu_synced_at?: string | null;
  feishu_source_updated_at?: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export type DeviationInvestigationPushRecordItem = FeishuDeviationInvestigationPushRecordItem;

export interface FeishuDeviationLedgerRecordItem extends FeishuPageRecordBase {
  deviation_code: string;
  final_code: string | null;
  title: string;
  department: string | null;
  discovery_date: string | null;
  discovery_time: string | null;
  discovery_location?: string | null;
  status: DeviationStatus;
  level: string | null;
  root_cause_category: ReasonCategory | null;
  description: string | null;
  immediate_actions?: string | null;
  reporter_id: string | null;
  handler: string | null;
  discoverer?: string | null;
  ai_analysis?: AiAnalysis | null;
  investigation_records?: InvestigationRecord[] | null;
  review_opinions?: ReviewOpinion[] | null;
  attachments?: string[] | null;
  needs_cross_dept_review?: boolean | null;
  cross_dept_reviewers?: CrossDeptReviewer[] | null;
  affected_items: string | null;
  batch_number: string | null;
  has_occurred_before?: boolean | null;
  material_disposition?: string | null;
  corrective_actions?: string | null;
  root_cause_analysis?: string | null;
  investigation_completed_at?: string | null;
  close_time?: string | null;
  related_capa_codes?: string[] | null;
  related_capas?: Array<{
    id: string;
    capa_code: string;
  }> | null;
  returned_step: ApprovalStep | null;
  status_updated_at: string | null;
  report_content?: string | null;
  report_versions?: ReportVersion[] | null;
  feishu_base_table_id?: string | null;
  feishu_base_record_id?: string | null;
  feishu_sync_status?: string | null;
  feishu_last_sync_error?: string | null;
  feishu_last_sync_direction?: 'system_to_base' | 'base_to_system' | string | null;
  feishu_synced_at?: string | null;
  feishu_source_updated_at?: string | null;
  created_at: string;
  updated_at?: string;
}

export interface CreateFeishuDeviationLedgerRecordRequest {
  deviation_code?: string | null;
  title?: string | null;
  description?: string | null;
  affected_items?: string | null;
  batch_number?: string | null;
  product_batch?: string | null;
  level?: string | null;
  has_occurred_before?: boolean | null;
  root_cause_analysis?: string | null;
  investigation_completed_at?: string | null;
  corrective_actions?: string | null;
  material_disposition?: string | null;
  status?: DeviationStatus | null;
  is_closed?: boolean | null;
  close_time?: string | null;
}

export type UpdateFeishuDeviationLedgerRecordRequest =
  Partial<CreateFeishuDeviationLedgerRecordRequest>;

export interface CreateDeviationInvestigationPushRecordRequest {
  deviation_id?: string | null;
  deviation_code?: string | null;
  push_round: string;
  investigation_report_url: string;
  submitted_at?: string | null;
  submitter_open_id: string;
  department_head?: string | null;
  department_head_result?: string | null;
  department_head_reviewed_at?: string | null;
  qa_name?: string | null;
  qa_result?: string | null;
  qa_reviewed_at?: string | null;
  qa_head_name?: string | null;
  qa_head_result?: string | null;
  qa_head_reviewed_at?: string | null;
}

export type UpdateDeviationInvestigationPushRecordRequest =
  Partial<CreateDeviationInvestigationPushRecordRequest>;

export interface CapaPlanTrackItem {
  id: string;
  capa_id: string;
  capa_code: string;
  plan_content: string;
  due_date: string | null;
  owner_name: string | null;
  owner_confirmed: boolean;
  department_head: string | null;
  department_head_confirmed: boolean;
  progress: string | null;
  reminder_status: string;
  linked_capa_code?: string | null;
  feishu_base_table_id?: string | null;
  feishu_base_record_id?: string | null;
  feishu_sync_status?: string | null;
  feishu_last_sync_error?: string | null;
  feishu_last_sync_direction?: 'system_to_base' | 'base_to_system' | string | null;
  feishu_synced_at?: string | null;
  feishu_source_updated_at?: string | null;
  created_at: string;
  updated_at: string;
}

export type QualityPullEntityCode =
  | 'deviation_ledger'
  | 'deviation_report_record'
  | 'deviation_investigation_push_record'
  | 'capa_ledger'
  | 'capa_plan_track';

export interface QualityPullSyncResult {
  entity_code?: QualityPullEntityCode | null;
  entity_label?: string | null;
  synced: number;
  failed: number;
  conflicts: number;
}

export interface QualitySyncConflictItem {
  entity_type: 'deviation' | 'capa' | 'deviation_investigation_push_record' | 'capa_plan_track';
  entity_label: string;
  entity_id: string;
  record_code: string;
  record_title?: string | null;
  route_path: string;
  feishu_base_table_id?: string | null;
  feishu_base_record_id?: string | null;
  feishu_sync_status: string;
  feishu_last_sync_error?: string | null;
  feishu_last_sync_direction?: 'system_to_base' | 'base_to_system' | string | null;
  feishu_synced_at?: string | null;
  feishu_source_updated_at?: string | null;
  updated_at: string;
  created_at: string;
}

export interface QualityFeishuAppSettingsDetail {
  app_id: string;
  app_secret_masked?: string | null;
  is_enabled: boolean;
  last_test_status?: string | null;
  last_test_error?: string | null;
  last_tested_at?: string | null;
}

export interface UpdateQualityFeishuAppSettingsRequest {
  app_id: string;
  app_secret: string;
  is_enabled: boolean;
}

export interface QualityFeishuEntitySettingItem {
  entity_code: string;
  entity_name: string;
  entity_group: string;
  source_note?: string | null;
  app_token?: string | null;
  base_table_name?: string | null;
  base_table_id?: string | null;
  is_enabled: boolean;
  enable_push_to_feishu: boolean;
  enable_pull_from_feishu: boolean;
  field_mappings?: QualityFeishuFieldMappingItem[];
  sort_order: number;
  last_sync_status?: string | null;
  last_sync_error?: string | null;
  last_synced_at?: string | null;
}

export interface UpdateQualityFeishuEntitySettingRequest {
  app_token?: string | null;
  base_table_name?: string | null;
  base_table_id?: string | null;
  is_enabled: boolean;
  enable_push_to_feishu: boolean;
  enable_pull_from_feishu: boolean;
  field_mappings?: QualityFeishuFieldMappingItem[] | null;
}

export interface QualityFeishuSettingsTestResult {
  success: boolean;
  message: string;
  checked_at: string;
  entity_code?: string | null;
  table_id?: string | null;
}

export interface QualityFeishuTableOption {
  table_id: string;
  table_name: string;
}

export interface QualityFeishuFieldOption {
  field_id: string;
  field_name: string;
  field_type?: string | number | null;
}

export interface QualityFeishuSystemFieldOption {
  field_key: string;
  field_label: string;
  direction: string;
}

export interface QualityFeishuFieldMappingItem {
  system_field: string;
  feishu_field?: string | null;
}

export interface QualityFeishuEntityFieldMappingBundle {
  entity_code: string;
  entity_name: string;
  system_fields: QualityFeishuSystemFieldOption[];
  feishu_fields: QualityFeishuFieldOption[];
  field_mappings: QualityFeishuFieldMappingItem[];
}

export interface CreateCapaPlanTrackRequest {
  capa_id: string;
  plan_content: string;
  due_date?: string | null;
  owner_name?: string | null;
  owner_confirmed?: boolean;
  department_head?: string | null;
  department_head_confirmed?: boolean;
  progress?: string | null;
  reminder_status?: string;
}

export type UpdateCapaPlanTrackRequest = Partial<CreateCapaPlanTrackRequest>;

// ============ Validation Types ============
export type ValidationType =
  | 'equipment_qualification'
  | 'process_validation'
  | 'cleaning_validation'
  | 'other_validation';

export interface CreateValidationRequest {
  title?: string;
  validation_type?: string;
  status?: string | null;
  department?: string | null;
  equipment_code?: string | null;
  product_codes?: string[] | string | null;
  planned_end_date?: string | null;
  group_chat?: string | null;
  participants?: string | null;
  owner_name?: string | null;
  plan_name?: string | null;
  plan_code?: string | null;
  drafted_at?: string | null;
  approved_at?: string | null;
  report_no?: string | null;
  drafted_at_1?: string | null;
  approved_at_1?: string | null;
  revalidation_cycle_years?: number | null;
}

export type UpdateValidationRequest = Partial<CreateValidationRequest>;

export interface ValidationListQuery {
  page?: number;
  page_size?: number;
  validation_type?: string;
  status?: string;
  department?: string;
  keyword?: string;
}

export type ValidationListItem = CreateValidationRequest & {
  id: string;
  created_at: string;
  updated_at: string;
  title?: string;
  validation_type?: string;
  status?: string | null;
  department?: string | null;
  equipment_code?: string | null;
  product_codes?: string[] | string | null;
  planned_end_date?: string | null;
  group_chat?: string | null;
  participants?: string | null;
  owner_name?: string | null;
  plan_name?: string | null;
  plan_code?: string | null;
  drafted_at?: string | null;
  approved_at?: string | null;
  report_no?: string | null;
  drafted_at_1?: string | null;
  approved_at_1?: string | null;
  revalidation_cycle_years?: number | null;
};

export interface ValidationExecutionItem {
  id: string;
  master_validation_id: string;
  title: string;
  status?: string | null;
  department?: string | null;
  product_codes?: string[] | string | null;
  group_chat?: string | null;
  participants?: string | null;
  owner_name?: string | null;
  plan_name?: string | null;
  plan_code?: string | null;
  drafted_at?: string | null;
  approved_at?: string | null;
  report_no?: string | null;
  drafted_at_1?: string | null;
  approved_at_1?: string | null;
  revalidation_cycle_years?: number | null;
  created_at: string;
  updated_at: string;
}

export interface UpdateValidationExecutionRequest {
  group_chat?: string | null;
  participants?: string | null;
  owner_name?: string | null;
  plan_name?: string | null;
  plan_code?: string | null;
  drafted_at?: string | null;
  approved_at?: string | null;
  report_no?: string | null;
  drafted_at_1?: string | null;
  approved_at_1?: string | null;
  revalidation_cycle_years?: number | null;
}

export type ValidationDetail = ValidationListItem & {
  created_by: string | null;
  updated_by: string | null;
};

export type ValidationFilters = ValidationListQuery;

export interface ValidationListResponse {
  items: ValidationListItem[];
  total: number;
  page: number;
  page_size: number;
}

/** 飞书验证记录条目（来源于飞书 Base） */
export interface FeishuValidationItem {
  record_id: string;
  table_id?: string | null;
  validation_type?: string;
  record_code?: string;
  title?: string;
  status?: string | null;
  department?: string | null;
  equipment_code?: string | null;
  product_codes?: string[] | null;
  planned_end_date?: string | null;
  group_chat?: string | null;
  participants?: string | null;
  owner_name?: string | null;
  plan_name?: string | null;
  plan_code?: string | null;
  drafted_at?: string | null;
  approved_at?: string | null;
  report_no?: string | null;
  drafted_at_1?: string | null;
  approved_at_1?: string | null;
  revalidation_cycle_years?: number | null;
  created_at?: string;
  updated_at?: string;
}

/** 飞书验证记录拉取结果 */
export interface FeishuValidationPullResult {
  synced: number;
  failed: number;
}

export interface QualityAiApplicableField {
  field_key: string;
  label: string;
  description?: string | null;
}

export interface QualityAiAnalysisLog {
  id: string;
  entity_type: 'deviation' | 'capa' | 'change';
  entity_id: string;
  analysis_type: string;
  input_snapshot: QualityAiInputSnapshot;
  output_payload: {
    summary?: string;
    risk_level?: string;
    risks?: string[];
    suggestions?: string[];
    missing_info?: string[];
    structured_fields?: QualityAiStructuredFields;
    disclaimer?: string;
  } | null;
  model_name: string;
  status: string;
  error_message?: string | null;
  is_applied: boolean;
  created_at: string;
  created_by?: string | null;
  applied_at?: string | null;
  applied_by?: string | null;
  applicable_fields: QualityAiApplicableField[];
}

export interface QualityAiLogListResponse {
  items: QualityAiAnalysisLog[];
  total: number;
}

export interface DeviationAiSessionAttachment {
  id: string;
  file_name: string;
  file_type: string;
  file_size: number;
  parse_status: string;
  parse_error?: string | null;
  parsed_summary?: string | null;
}

export interface DeviationAiSessionResultPayload {
  summary: string;
  risk_level: string;
  risks: string[];
  suggestions: string[];
  missing_info: string[];
  structured_fields: Record<string, string>;
  disclaimer?: string | null;
  applicable_fields: QualityAiApplicableField[];
}

export interface DeviationAiSession {
  id: string;
  deviation_id: string;
  supplement_text: string;
  status: string;
  error_message?: string | null;
  attachments: DeviationAiSessionAttachment[];
  deviation_analysis_payload: DeviationAiSessionResultPayload | null;
  capa_suggestion_payload: DeviationAiSessionResultPayload | null;
  last_generated_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface DeviationAiWorkbenchRecord {
  id: string;
  deviation_code: string;
  title: string;
  department: string | null;
  status: DeviationStatus;
  discovery_date: string | null;
}

// ============ Dashboard Statistics ============
export interface DeviationDashboardStats {
  total: number
  pending: number
  closedCount: number
  departmentDistribution: Array<{
    name: string
    count: number
  }>
  statusDistribution: Array<{
    status: string
    count: number
  }>
  levelDistribution: Array<{
    level: string
    count: number
  }>
  rootCauseDistribution: Array<{
    category: string
    count: number
  }>
  stepBreakdown: Array<{
    step: string
    label: string
    roleLabel: string
    count: number
  }>
}

export interface CapaDashboardStats {
  total: number
  closedCount: number
  overdueCount: number
  statusDistribution: Array<{
    status: string
    count: number
  }>
  sourceDistribution: Array<{
    source: string
    count: number
  }>
  categoryDistribution: Array<{
    category: string
    count: number
  }>
  departmentDistribution: Array<{
    name: string
    count: number
  }>
}

export interface ChangeDashboardStats {
  total: number
  closedCount: number
  delayCount: number
  statusDistribution: Array<{
    status: string
    count: number
  }>
  levelDistribution: Array<{
    level: string
    count: number
  }>
  typeDistribution: Array<{
    type: string
    count: number
  }>
  departmentDistribution: Array<{
    name: string
    count: number
  }>
  actionPlanTotal: number
  actionPlanOverdue: number
  actionPlanConfirmed: number
}

export interface ValidationDashboardStats {
  total: number
  typeDistribution: Array<{
    validation_type: string
    count: number
  }>
  statusDistribution: Array<{
    status: string
    count: number
  }>
  executionDistribution: Array<{
    validation_type: string
    count: number
  }>
  revalidationUpcoming: number
}

// ============ Department Contact Types ============
export interface DepartmentContact {
  id: string;
  name: string | null;
  department: string;
  enterprise_email: string | null;
  open_id: string | null;
  department_head_name: string | null;
  department_head_enterprise_email: string | null;
  department_head_open_id: string | null;
  feishu_record_id: string | null;
  created_at: string;
  updated_at: string;
}

// ============ Department Weekly Confirmation Types ============
export type ProductionStatus = 'production' | 'stopped';
export type DeviationConfirmationStatus = 'submitted' | 'unsubmitted';

export interface DepartmentWeeklyConfirmation {
  id: string;
  department: string;
  week_key: string;
  production_status: ProductionStatus;
  deviation_status: DeviationConfirmationStatus;
  confirmed_by_id: string | null;
  confirmed_at: string | null;
  created_at: string;
  updated_at: string;
}

// ============ Filter Types ============
export interface DeviationFilters {
  status?: DeviationStatus | '';
  level?: DeviationLevel | '';
  department?: string | '';
  keyword?: string;
  page?: number;
  page_size?: number;
}

export interface CapaFilters {
  status?: CapaWorkflowStatus | '';
  source?: CapaSource | '';
  category?: CapaCategory | '';
  keyword?: string;
  page?: number;
  page_size?: number;
}

export interface ChangeFilters {
  change_code?: string;
  applicant_department?: string;
  change_object?: string;
  change_level?: string;
  application_date_from?: string;
  application_date_to?: string;
  planned_approval_date_from?: string;
  planned_approval_date_to?: string;
  execution_date_from?: string;
  execution_date_to?: string;
  closure_date_from?: string;
  closure_date_to?: string;
  content_keyword?: string;
  page?: number;
  page_size?: number;
}

// ============ List Response Types ============
export interface DeviationListResponse {
  items: DeviationListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface CapaListResponse {
  items: CapaListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface ChangeListResponse {
  items: ChangeListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface DepartmentContactListResponse {
  items: DepartmentContact[];
  total: number;
  page: number;
  page_size: number;
}

// ============ Create/Update Request Types ============
export interface CreateDeviationRequest {
  title?: string | null;
  department?: string | null;
  reporter_open_id?: string | null;
  discovery_date?: string | null;
  discovery_time?: string | null;
  discovery_location?: string | null;
  level?: DeviationLevel | null;
  root_cause_category?: ReasonCategory | null;
  description?: string | null;
  immediate_actions?: string | null;
  attachments?: string[] | null;
  affected_items?: string | null;
  batch_number?: string | null;
  handler?: string | null;
  needs_cross_dept_review?: boolean | null;
  cross_dept_reviewers?: CrossDeptReviewer[] | null;
  has_occurred_before?: boolean | null;
  material_disposition?: string | null;
  corrective_actions?: string | null;
  root_cause_analysis?: string | null;
  investigation_completed_at?: string | null;
  is_closed?: boolean | null;
  close_time?: string | null;
}

export interface UpdateDeviationRequest {
  title?: string;
  status?: DeviationStatus;
  level?: DeviationLevel | null;
  department?: string | null;
  discovery_date?: string | null;
  discovery_time?: string | null;
  discovery_location?: string | null;
  root_cause_category?: ReasonCategory | null;
  description?: string | null;
  immediate_actions?: string | null;
  ai_analysis?: AiAnalysis | null;
  investigation_records?: InvestigationRecord[] | null;
  review_opinions?: ReviewOpinion[] | null;
  attachments?: string[] | null;
  final_code?: string | null;
  handler?: string | null;
  discoverer?: string | null;
  needs_cross_dept_review?: boolean | null;
  cross_dept_reviewers?: CrossDeptReviewer[] | null;
  affected_items?: string | null;
  batch_number?: string | null;
  has_occurred_before?: boolean | null;
  material_disposition?: string | null;
  corrective_actions?: string | null;
  root_cause_analysis?: string | null;
  investigation_completed_at?: string | null;
  is_closed?: boolean | null;
  close_time?: string | null;
  returned_step?: ApprovalStep | null;
  report_content?: string | null;
  report_versions?: ReportVersion[] | null;
}

export interface CreateCapaRequest {
  title?: string;
  deviation_id?: string | null;
  source?: string | null;
  source_code?: string | null;
  category?: CapaCategory | null;
  root_cause_category?: ReasonCategory | null;
  non_conformity_description?: string | null;
  root_cause_analysis?: string | null;
  capa_content?: string | null;
  capa_items?: CapaItem[] | null;
  executors?: string[] | null;
  expected_completion_date?: string | null;
  reporter?: string | null;
}

export interface UpdateCapaRequest {
  title?: string;
  status?: CapaWorkflowStatus;
  source?: string | null;
  source_code?: string | null;
  category?: CapaCategory | null;
  root_cause_category?: ReasonCategory | null;
  non_conformity_description?: string | null;
  root_cause_analysis?: string | null;
  capa_content?: string | null;
  capa_items?: CapaItem[] | null;
  executors?: string[] | null;
  expected_completion_date?: string | null;
  qa_reviewer_id?: string | null;
  qa_review_opinion?: string | null;
  qa_review_time?: string | null;
  q_head_approver_id?: string | null;
  q_head_approval_opinion?: string | null;
  q_head_approval_time?: string | null;
  execution_status?: string | null;
  execution_tracks?: ExecutionTrack[] | null;
  dept_head_confirmations?: DeptHeadConfirmation[] | null;
  evaluation_result?: string | null;
  evaluation_target?: string | null;
  evaluation_deadline?: string | null;
  evaluation_confirmer_id?: string | null;
  evaluation_confirm_date?: string | null;
  closure_date?: string | null;
  closure_remark?: string | null;
  final_code?: string | null;
  report_content?: string | null;
  report_versions?: ReportVersion[] | null;
  returned_step?: string | null;
  reporter?: string | null;
  reason_category?: string | null;
  department?: string | null;
  affected_product?: string | null;
}

export interface CreateChangeRequest {
  serial_number?: string | null;
  change_code: string;
  applicant_department?: string | null;
  change_object?: string | null;
  change_content?: string | null;
  change_level?: string | null;
  application_date?: string | null;
  planned_approval_date?: string | null;
  execution_date?: string | null;
  closure_date?: string | null;
}

export interface UpdateChangeRequest {
  serial_number?: string | null;
  change_code?: string | null;
  applicant_department?: string | null;
  change_object?: string | null;
  change_content?: string | null;
  change_level?: string | null;
  application_date?: string | null;
  planned_approval_date?: string | null;
  execution_date?: string | null;
  closure_date?: string | null;
}

export interface CreateDepartmentContactRequest {
  name: string;
  department: string;
  enterprise_email?: string | null;
  open_id?: string | null;
  department_head_name?: string | null;
  department_head_enterprise_email?: string | null;
  department_head_open_id?: string | null;
  feishu_record_id?: string | null;
}

export interface UpdateDepartmentContactRequest {
  name?: string | null;
  department?: string | null;
  enterprise_email?: string | null;
  open_id?: string | null;
  department_head_name?: string | null;
  department_head_enterprise_email?: string | null;
  department_head_open_id?: string | null;
  feishu_record_id?: string | null;
}


// ============ File Attachment Types ============
export interface FileAttachmentInfo {
  bucketId?: string;
  fileName?: string;
  filePath?: string;
  downloadUrl?: string;
}

// ============ Report Version Types ============
export interface ReportVersion {
  content: string;
  editor: string;
  editTime: string;
  changeSummary?: string;
}

// ============ Attachment Review Types ============
export interface AttachmentReview {
  id: string;
  deviation_id?: string;
  capa_id?: string;
  attachment_url: string;
  reviewer_id: string;
  review_time?: string;
  content: string;
  status: string;
  created_at: string;
  updated_at: string;
}
