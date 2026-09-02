'use server'

import { revalidatePath } from 'next/cache'
import { API_BASE_URL, actionFetch } from './quality-shared'
import type { components } from '@/types/generated/schema'
import type { InspectionFeishuFields } from '@/types/quality'

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
