import { logger } from '@lark-apaas/client-toolkit/logger';
import { axiosForBackend } from '@lark-apaas/client-toolkit/utils/getAxiosForBackend';
import type {
  AuditStats,
  PaginatedResponse,
  PointMapping,
  AuditRecordItem,
  BatchAuditResponse,
  CheckUniqueResponse,
  CreateManualRecordRequest,
  PressureRecordQuery,
  PressureRecordItem,
  CreateOcrRecordRequest,
  OcrSubmitResponse,
  PointMappingQuery,
  CreatePointMappingRequest,
  BatchManualEntryRequest,
  BatchManualEntryResponse,
  OcrTaskItem,
  CreateOcrTaskRequest,
  OcrResultData,
  SubmitOcrTaskResultRequest,
  NotificationListResponse,
  AreaExportData,
  MergedPressureResponse,
  DeleteMergedRowRequest,
  UpdateMergedRowRequest,
  UpdateMergedRowResponse,
} from '@shared/api.interface';

export async function getAuditStats(): Promise<AuditStats> {
  try {
    const response = await axiosForBackend({
      url: '/api/audit/stats',
      method: 'GET',
    });
    return response.data;
  } catch (error) {
    logger.error('获取审核统计失败', error);
    throw error;
  }
}

export async function getPendingRecords(
  page: number,
  pageSize: number,
): Promise<PaginatedResponse<AuditRecordItem>> {
  try {
    const response = await axiosForBackend({
      url: '/api/audit/pending-records',
      method: 'GET',
      params: { page, pageSize },
    });
    return response.data;
  } catch (error) {
    logger.error('获取待审核记录失败', error);
    throw error;
  }
}

export async function auditRecord(
  id: string,
  status: string,
  rejectReason?: string,
): Promise<{ success: boolean }> {
  try {
    const response = await axiosForBackend({
      url: `/api/pressure-records/${id}/audit`,
      method: 'PATCH',
      data: { status, rejectReason },
    });
    return response.data;
  } catch (error) {
    logger.error('审核记录失败', error);
    throw error;
  }
}

export async function batchAuditRecords(
  ids: string[],
  status: string,
  rejectReason?: string,
): Promise<BatchAuditResponse> {
  try {
    const response = await axiosForBackend({
      url: '/api/pressure-records/batch-audit',
      method: 'PATCH',
      data: { ids, status, rejectReason },
    });
    return response.data;
  } catch (error) {
    logger.error('批量审核记录失败', error);
    throw error;
  }
}

export async function getPressureRecords(
  params: PressureRecordQuery,
): Promise<PaginatedResponse<PressureRecordItem>> {
  try {
    const response = await axiosForBackend({
      url: '/api/pressure-records',
      method: 'GET',
      params,
    });
    return response.data;
  } catch (error) {
    logger.error('获取压差记录列表失败', error);
    throw error;
  }
}

export async function getPressureRecordDetail(
  id: string,
): Promise<PressureRecordItem> {
  try {
    const response = await axiosForBackend({
      url: `/api/pressure-records/${id}`,
      method: 'GET',
    });
    return response.data;
  } catch (error) {
    logger.error('获取压差记录详情失败', error);
    throw error;
  }
}

export async function submitOcrRecords(
  data: CreateOcrRecordRequest,
): Promise<OcrSubmitResponse> {
  try {
    const response = await axiosForBackend({
      url: '/api/pressure-records/ocr',
      method: 'POST',
      data,
    });
    return response.data;
  } catch (error) {
    logger.error('提交OCR识别记录失败', error);
    throw error;
  }
}

export async function getPointMappings(): Promise<PaginatedResponse<PointMapping>> {
  try {
    const response = await axiosForBackend({
      url: '/api/point-mappings',
      method: 'GET',
      params: { pageSize: 100 },
    });
    return response.data;
  } catch (error) {
    logger.error('获取位点列表失败', error);
    throw error;
  }
}

export async function checkPointIdUnique(
  pointId: string,
): Promise<CheckUniqueResponse> {
  try {
    const response = await axiosForBackend({
      url: '/api/point-mappings/check-unique',
      method: 'GET',
      params: { pointId },
    });
    return response.data;
  } catch (error) {
    logger.error('校验位点唯一性失败', error);
    throw error;
  }
}

export async function submitManualRecord(
  data: CreateManualRecordRequest,
): Promise<{ success: boolean }> {
  try {
    const response = await axiosForBackend({
      url: '/api/pressure-records/manual',
      method: 'POST',
      data,
    });
    return response.data;
  } catch (error) {
    logger.error('提交手动记录失败', error);
    throw error;
  }
}

export async function submitBatchManual(
  data: BatchManualEntryRequest,
): Promise<BatchManualEntryResponse> {
  try {
    const response = await axiosForBackend({
      url: '/api/pressure-records/manual/batch',
      method: 'POST',
      data,
    });
    return response.data;
  } catch (error) {
    logger.error('提交批量手动记录失败', error);
    throw error;
  }
}

export async function getExportByArea(
  params: PressureRecordQuery,
): Promise<AreaExportData[]> {
  try {
    const response = await axiosForBackend({
      url: '/api/pressure-records/export/by-area',
      method: 'GET',
      params,
    });
    return response.data;
  } catch (error) {
    logger.error('获取导出数据失败', error);
    throw error;
  }
}

export async function getMergedPressureRecords(
  params: PressureRecordQuery,
): Promise<MergedPressureResponse> {
  try {
    const response = await axiosForBackend({
      url: '/api/pressure-records/merged',
      method: 'GET',
      params,
    });
    return response.data;
  } catch (error) {
    logger.error('获取合并压差记录失败', error);
    throw error;
  }
}

export async function deleteMergedPressureRow(
  data: DeleteMergedRowRequest,
): Promise<{ successCount: number; success: boolean }> {
  try {
    const response = await axiosForBackend({
      url: '/api/pressure-records/merged/delete',
      method: 'POST',
      data,
    });
    return response.data;
  } catch (error) {
    logger.error('删除合并压差记录失败', error);
    throw error;
  }
}

export async function batchDeleteMergedPressureRows(
  rows: DeleteMergedRowRequest[],
): Promise<{ successCount: number; failCount: number; success: boolean }> {
  try {
    const response = await axiosForBackend({
      url: '/api/pressure-records/merged/batch-delete',
      method: 'POST',
      data: { rows },
    });
    return response.data;
  } catch (error) {
    logger.error('批量删除合并压差记录失败', error);
    throw error;
  }
}

export async function updateMergedPressureRow(
  data: UpdateMergedRowRequest,
): Promise<UpdateMergedRowResponse> {
  try {
    const response = await axiosForBackend({
      url: '/api/pressure-records/merged/update',
      method: 'POST',
      data,
    });
    return response.data;
  } catch (error) {
    logger.error('更新压差记录失败', error);
    throw error;
  }
}

export * as dashboard from './dashboard';

export async function getPointMappingList(
  params: PointMappingQuery,
): Promise<PaginatedResponse<PointMapping>> {
  try {
    const response = await axiosForBackend({
      url: '/api/point-mappings',
      method: 'GET',
      params,
    });
    return response.data;
  } catch (error) {
    logger.error('获取位点列表失败', error);
    throw error;
  }
}

export async function checkPointUnique(
  pointId: string,
): Promise<CheckUniqueResponse> {
  try {
    const response = await axiosForBackend({
      url: '/api/point-mappings/check-unique',
      method: 'GET',
      params: { pointId },
    });
    return response.data;
  } catch (error) {
    logger.error('校验位点唯一性失败', error);
    throw error;
  }
}

export async function createPointMapping(
  data: CreatePointMappingRequest,
): Promise<PointMapping> {
  try {
    const response = await axiosForBackend({
      url: '/api/point-mappings',
      method: 'POST',
      data,
    });
    return response.data;
  } catch (error) {
    logger.error('创建位点失败', error);
    throw error;
  }
}

export async function updatePointMapping(
  id: string,
  data: CreatePointMappingRequest,
): Promise<PointMapping> {
  try {
    const response = await axiosForBackend({
      url: `/api/point-mappings/${id}`,
      method: 'PUT',
      data,
    });
    return response.data;
  } catch (error) {
    logger.error('更新位点失败', error);
    throw error;
  }
}

export async function deletePointMapping(
  id: string,
): Promise<{ success: boolean }> {
  try {
    const response = await axiosForBackend({
      url: `/api/point-mappings/${id}`,
      method: 'DELETE',
    });
    return response.data;
  } catch (error) {
    logger.error('删除位点失败', error);
    throw error;
  }
}

export async function createOcrTask(
  data: CreateOcrTaskRequest,
): Promise<{ taskId: string }> {
  try {
    const response = await axiosForBackend({
      url: '/api/ocr-tasks',
      method: 'POST',
      data,
    });
    return response.data;
  } catch (error) {
    logger.error('创建OCR任务失败', error);
    throw error;
  }
}

export async function getOcrTasks(): Promise<OcrTaskItem[]> {
  try {
    const response = await axiosForBackend({
      url: '/api/ocr-tasks',
      method: 'GET',
    });
    return response.data;
  } catch (error) {
    logger.error('获取OCR任务列表失败', error);
    throw error;
  }
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function isValidUuid(value: string): boolean {
  return UUID_RE.test(value);
}

export async function getOcrTaskDetail(id: string): Promise<OcrTaskItem> {
  if (!isValidUuid(id)) {
    throw new Error(`Invalid task ID: ${id}`);
  }
  try {
    const response = await axiosForBackend({
      url: `/api/ocr-tasks/${id}`,
      method: 'GET',
    });
    return response.data;
  } catch (error) {
    logger.error('获取OCR任务详情失败', error);
    throw error;
  }
}

export async function submitOcrTaskResult(
  taskId: string,
  result: OcrResultData,
): Promise<{ success: boolean }> {
  try {
    const response = await axiosForBackend({
      url: `/api/ocr-tasks/${taskId}/result`,
      method: 'POST',
      data: result,
    });
    return response.data;
  } catch (error) {
    logger.error('提交OCR任务结果失败', error);
    throw error;
  }
}

export async function submitOcrTaskError(
  taskId: string,
  errorMessage: string,
): Promise<{ success: boolean }> {
  try {
    const response = await axiosForBackend({
      url: `/api/ocr-tasks/${taskId}/error`,
      method: 'POST',
      data: { errorMessage },
    });
    return response.data;
  } catch (error) {
    logger.error('提交OCR任务错误失败', error);
    throw error;
  }
}

export async function cancelOcrTask(taskId: string): Promise<{ success: boolean }> {
  try {
    const response = await axiosForBackend({
      url: `/api/ocr-tasks/${taskId}/cancel`,
      method: 'PATCH',
    });
    return response.data;
  } catch (error) {
    logger.error('取消OCR任务失败', error);
    throw error;
  }
}

export async function retryOcrTask(taskId: string): Promise<{ taskId: string }> {
  try {
    const response = await axiosForBackend({
      url: `/api/ocr-tasks/${taskId}/retry`,
      method: 'POST',
    });
    return response.data;
  } catch (error) {
    logger.error('重试OCR任务失败', error);
    throw error;
  }
}

export async function deleteOcrTask(taskId: string): Promise<{ success: boolean }> {
  try {
    const response = await axiosForBackend({
      url: `/api/ocr-tasks/${taskId}`,
      method: 'DELETE',
    });
    return response.data;
  } catch (error) {
    logger.error('删除OCR任务失败', error);
    throw error;
  }
}

export async function submitOcrTaskRecords(
  taskId: string,
  data: SubmitOcrTaskResultRequest,
): Promise<OcrSubmitResponse> {
  try {
    const response = await axiosForBackend({
      url: `/api/ocr-tasks/${taskId}/submit`,
      method: 'POST',
      data,
    });
    return response.data;
  } catch (error) {
    logger.error('提交OCR任务记录失败', error);
    throw error;
  }
}

export async function deletePressureRecord(id: string): Promise<{ success: boolean }> {
  try {
    const response = await axiosForBackend({
      url: `/api/pressure-records/${id}`,
      method: 'DELETE',
    });
    return response.data;
  } catch (error) {
    logger.error('删除压差记录失败', error);
    throw error;
  }
}

export async function batchDeletePressureRecords(ids: string[]): Promise<{ successCount: number; failCount: number; success: boolean }> {
  try {
    const response = await axiosForBackend({
      url: '/api/pressure-records/batch-delete',
      method: 'POST',
      data: { ids },
    });
    return response.data;
  } catch (error) {
    logger.error('批量删除压差记录失败', error);
    throw error;
  }
}

export async function getNotifications(): Promise<NotificationListResponse> {
  try {
    const response = await axiosForBackend({
      url: '/api/notifications',
      method: 'GET',
    });
    return response.data;
  } catch (error) {
    logger.error('获取通知列表失败', error);
    throw error;
  }
}

export async function getUnreadCount(): Promise<{ count: number }> {
  try {
    const response = await axiosForBackend({
      url: '/api/notifications/unread-count',
      method: 'GET',
    });
    return response.data;
  } catch (error) {
    logger.error('获取未读通知数失败', error);
    throw error;
  }
}

export async function markNotificationRead(id: string): Promise<{ success: boolean }> {
  try {
    const response = await axiosForBackend({
      url: `/api/notifications/${id}/read`,
      method: 'PATCH',
    });
    return response.data;
  } catch (error) {
    logger.error('标记通知已读失败', error);
    throw error;
  }
}

export async function markAllNotificationsRead(): Promise<{ success: boolean }> {
  try {
    const response = await axiosForBackend({
      url: '/api/notifications/read-all',
      method: 'PATCH',
    });
    return response.data;
  } catch (error) {
    logger.error('标记所有通知已读失败', error);
    throw error;
  }
}

export async function ocrImageFile(
  file: File,
): Promise<{ result: Array<Record<string, unknown>> }> {
  const base64 = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      const commaIdx = result.indexOf(',');
      resolve(commaIdx >= 0 ? result.slice(commaIdx + 1) : result);
    };
    reader.onerror = () => reject(new Error('读取文件失败'));
    reader.readAsDataURL(file);
  });
  try {
    const response = await axiosForBackend({
      url: '/api/ocr',
      method: 'POST',
      data: { image: base64, mimetype: file.type },
    });
    return response.data;
  } catch (error) {
    logger.error('OCR图片识别失败', error);
    throw error;
  }
}

