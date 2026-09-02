'use server'

import { revalidatePath } from 'next/cache'
import { API_BASE_URL, actionFetch } from './quality-shared'

function revalidateQcValidationPaths() {
  revalidatePath('/quality')
  revalidatePath('/quality/validation')
  revalidatePath('/quality/validation/qc-validation')
}

/** 新增 QC验证记录（同步到多维表格）。字段名 = 飞书表真实字段名。 */
export async function createQcValidationRecord(
  year: number,
  fields: Record<string, unknown>
): Promise<{ record_id: string }> {
  const result = await actionFetch<{ record_id: string }>(
    `${API_BASE_URL}/api/v1/quality/validation-qc/records?year=${year}`,
    {
      method: 'POST',
      body: JSON.stringify({ fields }),
    }
  )
  if (!result) throw new Error('未收到QC验证创建结果')
  revalidateQcValidationPaths()
  return result
}

/** 编辑 QC验证记录（同步到多维表格）。只提交需写入的字段。 */
export async function updateQcValidationRecord(
  year: number,
  recordId: string,
  fields: Record<string, unknown>
): Promise<{ record_id: string }> {
  const result = await actionFetch<{ record_id: string }>(
    `${API_BASE_URL}/api/v1/quality/validation-qc/records/${encodeURIComponent(recordId)}?year=${year}`,
    {
      method: 'PUT',
      body: JSON.stringify({ fields }),
    }
  )
  if (!result) throw new Error('未收到QC验证更新结果')
  revalidateQcValidationPaths()
  return result
}

/** 删除 QC验证记录（同步到多维表格）。 */
export async function deleteQcValidationRecord(
  year: number,
  recordId: string
): Promise<{ record_id: string }> {
  const result = await actionFetch<{ record_id: string }>(
    `${API_BASE_URL}/api/v1/quality/validation-qc/records/${encodeURIComponent(recordId)}?year=${year}`,
    { method: 'DELETE' }
  )
  if (!result) throw new Error('未收到QC验证删除结果')
  revalidateQcValidationPaths()
  return result
}
