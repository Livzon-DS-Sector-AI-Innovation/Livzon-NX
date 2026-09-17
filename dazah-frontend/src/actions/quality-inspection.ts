'use server'

import { revalidatePath } from 'next/cache'
import { API_BASE_URL, actionFetch } from './quality-shared'
import type { components } from '@/types/generated/schema'
import type {
  InspectionFeishuFields,
  InstrumentCertificateAnalyzeResult,
  InstrumentCertificateRematchRequest,
  ItemsLowStockPushResult,
} from '@/types/quality'

function revalidateInspectionPaths() {
  revalidatePath('/quality')
  revalidatePath('/quality/inspection')
}

/** 新增检验飞书记录（同步到多维表格）。字段名 = 飞书表真实字段名。 */
export async function createInspectionFeishuRecord(
  entityCode: string,
  fields: InspectionFeishuFields
) {
  const result = await actionFetch<{ record_id: string }>(
    `${API_BASE_URL}/api/v1/quality/inspection/feishu/${encodeURIComponent(entityCode)}/records`,
    {
      method: 'POST',
      body: JSON.stringify({ fields } satisfies components['schemas']['InspectionFeishuRecordBody']),
    }
  )
  revalidateInspectionPaths()
  return result
}

/** 编辑检验飞书记录（同步到多维表格）。只提交发生变更的字段。 */
export async function updateInspectionFeishuRecord(
  entityCode: string,
  recordId: string,
  fields: InspectionFeishuFields
) {
  const result = await actionFetch<{ record_id: string }>(
    `${API_BASE_URL}/api/v1/quality/inspection/feishu/${encodeURIComponent(entityCode)}/records/${encodeURIComponent(recordId)}`,
    {
      method: 'PUT',
      body: JSON.stringify({ fields } satisfies components['schemas']['InspectionFeishuRecordBody']),
    }
  )
  revalidateInspectionPaths()
  return result
}

/** 删除检验飞书记录（同步到多维表格）。 */
export async function deleteInspectionFeishuRecord(entityCode: string, recordId: string) {
  const result = await actionFetch<{ record_id: string }>(
    `${API_BASE_URL}/api/v1/quality/inspection/feishu/${encodeURIComponent(entityCode)}/records/${encodeURIComponent(recordId)}`,
    { method: 'DELETE' }
  )
  revalidateInspectionPaths()
  return result
}

/** 按实体回拉检验飞书记录（同步按钮）。 */
export async function pullInspectionFeishuRecords(entityCode: string) {
  const result = await actionFetch<{ synced: number; failed: number }>(
    `${API_BASE_URL}/api/v1/quality/inspection/feishu/${encodeURIComponent(entityCode)}/pull`,
    { method: 'POST' }
  )
  revalidateInspectionPaths()
  return result
}

/** 一键推送库存不足物料到配置的接收人。 */
export async function pushItemsLowStock(): Promise<ItemsLowStockPushResult> {
  const result = await actionFetch<ItemsLowStockPushResult>(
    `${API_BASE_URL}/api/v1/quality/items/dashboard/push-low-stock`,
    { method: 'POST' }
  )
  return result ?? { status: 'failed', sent: 0, skipped: 0, failed: 0, item_count: 0, message: '推送失败' }
}

/** 测试推送库存不足物料（不写幂等、不影响真实去重）。 */
export async function pushItemsLowStockTest(): Promise<ItemsLowStockPushResult> {
  const result = await actionFetch<ItemsLowStockPushResult>(
    `${API_BASE_URL}/api/v1/quality/items/dashboard/push-low-stock/test`,
    { method: 'POST' }
  )
  return result ?? { status: 'failed', sent: 0, skipped: 0, failed: 0, item_count: 0, message: '推送失败' }
}

/**
 * 上传校准证书 → AI 识别 → 实时反查 QC 设备目录。
 * 只返回外部校准表的预填字段，不写飞书；记录由人工确认表单提交。
 */
export async function analyzeInstrumentCertificate(
  file: File
): Promise<InstrumentCertificateAnalyzeResult> {
  const formData = new FormData()
  formData.append('file', file)
  const result = await actionFetch<InstrumentCertificateAnalyzeResult>(
    `${API_BASE_URL}/api/v1/quality/instruments/cal-external/certificate-analyze`,
    { method: 'POST', body: formData }
  )
  if (!result) throw new Error('未收到证书识别结果')
  return result
}

/**
 * 人工修正识别字段后重新匹配（填入表单前）：
 * 按修正后的出厂编号重新反查 QC 设备目录、重算下次检定日期、刷新序号；
 * 附件复用首次识别上传的 token，不重复上传。
 */
export async function rematchInstrumentCertificate(
  payload: InstrumentCertificateRematchRequest
): Promise<InstrumentCertificateAnalyzeResult> {
  const result = await actionFetch<InstrumentCertificateAnalyzeResult>(
    `${API_BASE_URL}/api/v1/quality/instruments/cal-external/certificate-rematch`,
    { method: 'POST', body: JSON.stringify(payload) }
  )
  if (!result) throw new Error('未收到重新匹配结果')
  return result
}
