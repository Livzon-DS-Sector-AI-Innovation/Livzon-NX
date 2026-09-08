'use server'

import { revalidatePath } from 'next/cache'
import { API_BASE_URL, actionFetch } from './quality-shared'

function revalidateAnomalyReportPaths() {
  revalidatePath('/quality')
  revalidatePath('/quality/anomaly-report')
  for (const year of [2025, 2026, 2027, 2028]) {
    revalidatePath(`/quality/anomaly-report/${year}`)
  }
}

/** 新增成品异常报告记录（同步到多维表格）。字段名 = 飞书表真实字段名。 */
export async function createAnomalyReportRecord(
  year: number,
  fields: Record<string, unknown>
): Promise<{ record_id: string }> {
  const result = await actionFetch<{ record_id: string }>(
    `${API_BASE_URL}/api/v1/quality/finished-product-anomaly/records?year=${year}`,
    {
      method: 'POST',
      body: JSON.stringify({ fields }),
    }
  )
  if (!result) throw new Error('未收到成品异常报告创建结果')
  revalidateAnomalyReportPaths()
  return result
}

/** 编辑成品异常报告记录（同步到多维表格）。只提交需写入的字段。 */
export async function updateAnomalyReportRecord(
  year: number,
  recordId: string,
  fields: Record<string, unknown>
): Promise<{ record_id: string }> {
  const result = await actionFetch<{ record_id: string }>(
    `${API_BASE_URL}/api/v1/quality/finished-product-anomaly/records/${encodeURIComponent(recordId)}?year=${year}`,
    {
      method: 'PUT',
      body: JSON.stringify({ fields }),
    }
  )
  if (!result) throw new Error('未收到成品异常报告更新结果')
  revalidateAnomalyReportPaths()
  return result
}

/** 删除成品异常报告记录（同步到多维表格）。 */
export async function deleteAnomalyReportRecord(
  year: number,
  recordId: string
): Promise<{ record_id: string }> {
  const result = await actionFetch<{ record_id: string }>(
    `${API_BASE_URL}/api/v1/quality/finished-product-anomaly/records/${encodeURIComponent(recordId)}?year=${year}`,
    { method: 'DELETE' }
  )
  if (!result) throw new Error('未收到成品异常报告删除结果')
  revalidateAnomalyReportPaths()
  return result
}

/** 触发成品异常记录 AI 分类（后台 job，增量去重）。 */
export async function runAnomalyAnalysisAction(
  year?: number
): Promise<{ job_id: string; years: number[] }> {
  const query = year ? `?year=${year}` : ''
  const result = await actionFetch<{ job_id: string; years: number[] }>(
    `${API_BASE_URL}/api/v1/quality/finished-product-anomaly/analysis/run${query}`,
    { method: 'POST' }
  )
  if (!result) throw new Error('未收到 AI 分析任务结果')
  revalidateAnomalyReportPaths()
  return result
}
