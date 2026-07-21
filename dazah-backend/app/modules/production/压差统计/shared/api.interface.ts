/* 前后端共享的类型写在这里 */

export const AREA_OPTIONS = [
  '无菌区',
  '精洗区',
  '配液区',
  '走廊',
  '更衣室',
  '其他',
] as const;
export type AreaType = (typeof AREA_OPTIONS)[number];

export const INPUT_TYPES = ['manual', 'ocr'] as const;
export type InputType = (typeof INPUT_TYPES)[number];

export const AUDIT_STATUSES = ['pending', 'approved', 'rejected'] as const;
export type AuditStatus = (typeof AUDIT_STATUSES)[number];

export const OCR_TASK_STATUSES = [
  'pending',
  'processing',
  'completed',
  'failed',
  'cancelled',
  'submitted',
] as const;
export type OcrTaskStatus = (typeof OCR_TASK_STATUSES)[number];

export interface DashboardStats {
  todayCount: number;
  pendingCount: number;
  lastRecordTime: string | null;
}

export interface PointMapping {
  id: string;
  pointId: string;
  area: AreaType;
  standardPressure: number;
}

export interface PressureRecordItem {
  id: string;
  pointId: string;
  area: AreaType;
  pressureValue: number;
  standardPressure: number;
  recordTime: string;
  inputType: InputType;
  status: AuditStatus;
  rejectReason: string | null;
  creator: string;
  imageUrl: string | null;
  remark: string | null;
  batchId: string | null;
  timeSlot: string | null;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
}

export interface PressureRecordQuery {
  area?: AreaType;
  startDate?: string;
  endDate?: string;
  pointId?: string;
  inputType?: InputType;
  status?: AuditStatus;
  page?: number;
  pageSize?: number;
}

export interface PointMappingQuery {
  area?: AreaType;
  keyword?: string;
  page?: number;
  pageSize?: number;
}

export interface CreateManualRecordRequest {
  recordTime: string;
  pointId: string;
  pressureValue: number;
  timeSlot?: string;
  remark?: string;
}

export interface BatchManualEntryRow {
  date: string;
  values: Record<string, number | null>;
}

export interface BatchManualEntryRequest {
  area: AreaType;
  rows: BatchManualEntryRow[];
  timeSlots?: string[];
  remark?: string;
}

export interface BatchManualEntryResponse {
  successCount: number;
  failCount: number;
  batchId: string;
}

export interface CreateOcrRecordRequest {
  records: Array<{
    recordTime: string;
    pointId: string;
    pressureValue: number;
    area: AreaType;
    standardPressure?: number;
    remark?: string;
  }>;
  imageUrl: string;
  taskId?: string;
}

export interface OcrSubmitResponse {
  successCount: number;
  failCount: number;
  success: boolean;
  batchId?: string;
}

export interface AuditRequest {
  status: 'approved' | 'rejected';
  rejectReason?: string;
}

export interface BatchAuditRequest {
  ids: string[];
  status: 'approved' | 'rejected';
  rejectReason?: string;
}

export interface BatchAuditResponse {
  successCount: number;
  failCount: number;
  success: boolean;
}

export interface CreatePointMappingRequest {
  pointId: string;
  area: AreaType;
  standardPressure: number;
}

export interface AuditStats {
  pendingCount: number;
  todayApprovedCount: number;
  rejectedCount: number;
}

export interface AuditRecordItem {
  id: string;
  pointId: string;
  area: AreaType;
  pressureValue: number;
  standardPressure: number;
  recordTime: string;
  inputType: InputType;
  creator: string;
}

export interface CheckUniqueResponse {
  exists: boolean;
}

export interface OcrTaskItem {
  id: string;
  status: OcrTaskStatus;
  imageUrl: string;
  result: OcrResultData | null;
  errorMessage: string | null;
  batchId: string | null;
  createdAt: string;
}

export interface OcrResultData {
  records: Array<{
    pointId: string;
    pressureValue: number;
    recordTime: string;
    recorder: string;
    timeSlot?: string;
  }>;
}

export interface CreateOcrTaskRequest {
  imageUrl: string;
}

export interface NotificationItem {
  id: string;
  type: string;
  title: string;
  message: string;
  isRead: boolean;
  relatedId: string | null;
  relatedType: string | null;
  createdAt: string;
}

export interface NotificationListResponse {
  items: NotificationItem[];
  unreadCount: number;
}

export interface TemplateExportRow {
  date: string;
  pointId: string;
  standardPressure: string;
  values: Record<string, number | null>;
}

export interface AreaExportData {
  area: AreaType;
  timeSlots: string[];
  rows: TemplateExportRow[];
}

export interface SubmitOcrTaskResultRequest {
  records: Array<{
    recordTime: string;
    pointId: string;
    pressureValue: number;
    area: AreaType;
    timeSlot?: string;
    standardPressure?: number;
    remark?: string;
  }>;
}

export interface DeleteRecordsRequest {
  ids: string[];
}

export interface DeleteRecordsResponse {
  successCount: number;
  failCount: number;
  success: boolean;
}

export const DATA_SOURCES = ['manual', 'ocr'] as const;
export type DataSource = (typeof DATA_SOURCES)[number];







export interface MergedPressureRow {
  pointId: string;
  area: AreaType;
  date: string;
  timeSlotValues: Record<string, number | null>;
  standardPressure: number;
  recordIds: string[];
  status: AuditStatus;
  inputType: InputType;
}

export interface MergedPressureResponse {
  items: MergedPressureRow[];
  total: number;
}

export interface DeleteMergedRowRequest {
  pointId: string;
  date: string;
}

export interface BatchDeleteMergedRowsRequest {
  rows: DeleteMergedRowRequest[];
}

export interface UpdateMergedRowRequest {
  pointId: string;
  date: string;
  timeSlotValues: Record<string, number | null>;
}

export interface UpdateMergedRowResponse {
  successCount: number;
  success: boolean;
}
