'use server'

import { getServerApiBaseUrl } from '@/lib/server-api'
import { revalidatePath } from 'next/cache'
import { getAuthHeaders } from '@/lib/auth'
import { requireActionResponse, serverActionResult, type BusinessErrorMessages } from '@/lib/server-action-result'
import { uncertainWriteMessage } from '@/lib/user-error'
import type { components } from '@/types/generated/schema'
import type {
  ContractGenerateRequest,
  InvoiceRecognitionRecordDeleteResponse,
  InvoiceRecognitionResponse,
  MaterialPriceFillPreviewApiResponse,
  MaterialSourceConfigApiResponse,
  MaterialSourceConfigUpsert,
  MaterialSourceProbeApiResponse,
  MaterialSourceSyncApiResponse,
  PurchaseApprovalRequest,
  PurchaseRequestApiResponse,
  PurchaseRequestCreate,
  PurchaseRequestDeleteResponse,
  PurchaseRequestImportResponse,
  PurchaseRequestUpdate,
  SupplierImportResponse,
} from '@/types/purchasing'

const API_BASE = getServerApiBaseUrl()

async function procurementHeaders(json = false): Promise<Record<string, string>> {
  const headers = await getAuthHeaders()
  if (!json) delete headers['Content-Type']
  return headers
}

export async function recognizeInvoicePdf(
  formData: FormData
): Promise<InvoiceRecognitionResponse> {
  const headers = await procurementHeaders()

  const response = await fetch(`${API_BASE}/api/v1/procurement/invoices/recognize`, {
    method: 'POST',
    headers,
    body: formData,
    cache: 'no-store',
  })

  return parseJsonResponse<InvoiceRecognitionResponse>(response, '发票识别失败')
}

type ProcurementErrorCode = components['schemas']['ProcurementErrorCode']

function procurementWrite<T>(
  operation: string,
  label: string,
  path: string,
  refreshPath: string,
  body?: FormData | string,
  businessMessages?: BusinessErrorMessages,
) {
  return serverActionResult(`procurement.${operation}`, async (): Promise<T> => {
    const response = await fetch(`${API_BASE}/api/v1/procurement${path}`, {
      method: 'POST',
      headers: await procurementHeaders(typeof body === 'string'),
      body,
      cache: 'no-store',
    })
    await requireActionResponse(response, businessMessages)
    const payload = await response.json()
    revalidatePath(refreshPath)
    return payload
  }, uncertainWriteMessage(label))
}

function invalidTableMessage(message: string) {
  const codes = { PROCUREMENT_IMPORT_TABLE_INVALID: message } satisfies Partial<Record<ProcurementErrorCode, string>>
  return { 422: codes }
}

export async function importSupplierTable(formData: FormData) {
  return procurementWrite<SupplierImportResponse>(
    'supplier.import', '供应商清单导入', '/suppliers/import', '/purchasing/supplier', formData,
    invalidTableMessage('无法读取供应商清单，请核对表头和数据后重新上传'),
  )
}

export async function importPurchaseRequestTable(formData: FormData) {
  return procurementWrite<PurchaseRequestImportResponse>(
    'purchaseRequest.import', '采购申请导入', '/purchase-requests/import', '/purchasing', formData,
    invalidTableMessage('无法读取采购申请表格，请使用有效的采购申请模板重新上传'),
  )
}

export async function deleteInvoiceRecognitionRecord(
  recordId: string
): Promise<InvoiceRecognitionRecordDeleteResponse> {
  const headers = await procurementHeaders()

  const response = await fetch(
    `${API_BASE}/api/v1/procurement/invoices/recognition-records/${recordId}`,
    {
      method: 'DELETE',
      headers,
      cache: 'no-store',
    }
  )

  return parseJsonResponse<InvoiceRecognitionRecordDeleteResponse>(
    response,
    '识别记录删除失败'
  )
}

export async function deleteInvoiceRecognitionRecords(
  recordIds: string[]
): Promise<InvoiceRecognitionRecordDeleteResponse> {
  const headers = await procurementHeaders(true)

  const response = await fetch(
    `${API_BASE}/api/v1/procurement/invoices/recognition-records/batch-delete`,
    {
      method: 'POST',
      headers,
      body: JSON.stringify({ ids: recordIds }),
      cache: 'no-store',
    }
  )

  return parseJsonResponse<InvoiceRecognitionRecordDeleteResponse>(
    response,
    '识别记录删除失败'
  )
}

export async function createPurchaseRequest(
  payload: PurchaseRequestCreate
): Promise<PurchaseRequestApiResponse> {
  const response = await procurementJsonFetch<PurchaseRequestApiResponse>(
    '/api/v1/procurement/purchase-requests',
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
    '采购申请保存失败'
  )
  revalidatePath('/purchasing')
  return response
}

export async function updatePurchaseRequest(
  requestId: string,
  payload: PurchaseRequestUpdate
): Promise<PurchaseRequestApiResponse> {
  const response = await procurementJsonFetch<PurchaseRequestApiResponse>(
    `/api/v1/procurement/purchase-requests/${requestId}`,
    {
      method: 'PUT',
      body: JSON.stringify(payload),
    },
    '采购申请更新失败'
  )
  revalidatePath('/purchasing')
  return response
}

export async function submitPurchaseRequest(requestId: string) {
  const codes = {
    PROCUREMENT_SUBMIT_ITEMS_MISSING: '请至少添加一条采购明细后重新提交',
    PROCUREMENT_SUBMIT_AMOUNT_MISMATCH: '明细金额与数量乘以单价不一致，请核对后重新提交',
  } satisfies Partial<Record<ProcurementErrorCode, string>>
  return procurementWrite<PurchaseRequestApiResponse>(
    'purchaseRequest.submit', '采购申请提交', `/purchase-requests/${encodeURIComponent(requestId)}/submit`,
    '/purchasing', '{}', { 422: codes },
  )
}

export async function deletePurchaseRequest(
  requestId: string
): Promise<PurchaseRequestDeleteResponse> {
  const response = await procurementJsonFetch<PurchaseRequestDeleteResponse>(
    `/api/v1/procurement/purchase-requests/${requestId}`,
    {
      method: 'DELETE',
    },
    '采购申请删除失败'
  )
  revalidatePath('/purchasing')
  return response
}

export async function approvePurchaseRequest(requestId: string, payload: PurchaseApprovalRequest) {
  return procurementWrite<PurchaseRequestApiResponse>(
    'purchaseRequest.approve', '采购审批通过', `/purchase-requests/${encodeURIComponent(requestId)}/approve`,
    '/purchasing', JSON.stringify(payload),
  )
}

export async function rejectPurchaseRequest(requestId: string, payload: PurchaseApprovalRequest) {
  return procurementWrite<PurchaseRequestApiResponse>(
    'purchaseRequest.reject', '采购审批驳回', `/purchase-requests/${encodeURIComponent(requestId)}/reject`,
    '/purchasing', JSON.stringify(payload),
  )
}

export type ContractGenerateActionResult =
  | {
      ok: true
      filename: string
      contentType: string
      base64: string
      recordId?: string
    }
  | {
      ok: false
      message: string
    }

export async function generateProcurementContract(
  payload: ContractGenerateRequest
): Promise<ContractGenerateActionResult> {
  const headers = await procurementHeaders(true)

  const response = await fetch(`${API_BASE}/api/v1/procurement/contracts/generate`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
    cache: 'no-store',
  })

  if (!response.ok) {
    let message = '合同生成失败'
    try {
      const errorBody = await response.json()
      message = errorBody.detail || errorBody.message || message
    } catch {
      message = `${message}: ${response.status} ${response.statusText}`
    }
    return { ok: false, message }
  }

  const contentType =
    response.headers.get('content-type') ||
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
  const filename =
    parseDownloadFilename(response.headers.get('content-disposition')) || '采购合同.docx'
  const arrayBuffer = await response.arrayBuffer()

  return {
    ok: true,
    filename,
    contentType,
    base64: Buffer.from(arrayBuffer).toString('base64'),
    recordId: response.headers.get('x-contract-record-id') || undefined,
  }
}

export type MaterialPriceFillDownload =
  | { ok: true; filename: string; base64: string; filledCount: number }
  | { ok: false; message: string }

export async function previewMaterialPriceFill(
  formData: FormData,
): Promise<MaterialPriceFillPreviewApiResponse> {
  const headers = await procurementHeaders()
  const response = await fetch(
    `${API_BASE}/api/v1/procurement/material-prices/fill/preview`,
    {
      method: 'POST',
      headers,
      body: formData,
      cache: 'no-store',
    },
  )
  return parseJsonResponse<MaterialPriceFillPreviewApiResponse>(
    response,
    '表格解析失败',
  )
}

export async function generateMaterialPriceFill(
  formData: FormData,
): Promise<MaterialPriceFillDownload> {
  const headers = await procurementHeaders()
  const response = await fetch(
    `${API_BASE}/api/v1/procurement/material-prices/fill`,
    {
      method: 'POST',
      headers,
      body: formData,
      cache: 'no-store',
    },
  )

  if (!response.ok) {
    let message = '表格补价失败'
    try {
      const errorBody = await response.json()
      message = errorBody.detail || errorBody.message || message
    } catch {
      message = `${message}: ${response.status} ${response.statusText}`
    }
    return { ok: false, message }
  }

  const filename =
    parseDownloadFilename(response.headers.get('content-disposition')) ||
    '补价结果.xlsx'
  const filledCount = Number(response.headers.get('x-filled-count') || 0)
  const arrayBuffer = await response.arrayBuffer()

  return {
    ok: true,
    filename,
    base64: Buffer.from(arrayBuffer).toString('base64'),
    filledCount: Number.isFinite(filledCount) ? filledCount : 0,
  }
}

export async function testProcurementMaterialSource(
  payload: MaterialSourceConfigUpsert,
): Promise<MaterialSourceProbeApiResponse> {
  return procurementJsonFetch<MaterialSourceProbeApiResponse>(
    '/api/v1/procurement/material-source-config/test',
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
    '物料数据源测试失败',
  )
}

export async function saveProcurementMaterialSource(
  payload: MaterialSourceConfigUpsert,
): Promise<MaterialSourceConfigApiResponse> {
  const response = await procurementJsonFetch<MaterialSourceConfigApiResponse>(
    '/api/v1/procurement/material-source-config',
    {
      method: 'PUT',
      body: JSON.stringify(payload),
    },
    '物料数据源保存失败',
  )
  revalidatePath('/purchasing')
  revalidatePath('/purchasing/settings')
  return response
}

export async function syncProcurementMaterialSource(): Promise<MaterialSourceSyncApiResponse> {
  const response = await procurementJsonFetch<MaterialSourceSyncApiResponse>(
    '/api/v1/procurement/material-source-config/sync',
    {
      method: 'POST',
      body: JSON.stringify({}),
    },
    '采购物料数据同步失败',
  )
  revalidatePath('/purchasing/material-library')
  revalidatePath('/purchasing/settings')
  return response
}

function parseDownloadFilename(contentDisposition: string | null) {
  if (!contentDisposition) return null

  const utf8Match = contentDisposition.match(/filename\*=utf-8''([^;]+)/i)
  if (utf8Match?.[1]) {
    return decodeURIComponent(utf8Match[1])
  }

  const asciiMatch = contentDisposition.match(/filename="?([^";]+)"?/i)
  return asciiMatch?.[1] ?? null
}

async function procurementJsonFetch<T extends { code: number; message: string }>(
  path: string,
  options: RequestInit,
  fallbackMessage: string
): Promise<T> {
  const headers = await procurementHeaders(true)

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    cache: 'no-store',
  })
  return parseJsonResponse<T>(response, fallbackMessage)
}

async function parseJsonResponse<T extends { code: number; message: string }>(
  response: Response,
  fallbackMessage: string
): Promise<T> {
  try {
    const body = await response.json()
    if (response.ok && typeof body?.code === 'number') {
      return body
    }

    return {
      code: typeof body?.code === 'number' ? body.code : response.status,
      message: body?.message || body?.detail || fallbackMessage,
      data: body?.data ?? null,
      meta: body?.meta ?? null,
    } as unknown as T
  } catch {
    return {
      code: response.status,
      message: `${fallbackMessage}: ${response.status} ${response.statusText}`,
      data: null,
      meta: null,
    } as unknown as T
  }
}
