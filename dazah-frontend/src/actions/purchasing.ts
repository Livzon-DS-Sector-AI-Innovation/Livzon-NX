'use server'

import { getServerApiBaseUrl } from '@/lib/server-api'
import { revalidatePath } from 'next/cache'
import { getAuthHeaders } from '@/lib/auth'
import type {
  ContractGenerateRequest,
  InvoiceRecognitionRecordDeleteResponse,
  InvoiceRecognitionResponse,
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

export async function importSupplierTable(
  formData: FormData
): Promise<SupplierImportResponse> {
  const headers = await procurementHeaders()

  const response = await fetch(`${API_BASE}/api/v1/procurement/suppliers/import`, {
    method: 'POST',
    headers,
    body: formData,
    cache: 'no-store',
  })
  const result = await parseJsonResponse<SupplierImportResponse>(
    response,
    '供应商清单导入失败'
  )
  if (response.ok) {
    revalidatePath('/purchasing/supplier')
  }
  return result
}

export async function importPurchaseRequestTable(
  formData: FormData
): Promise<PurchaseRequestImportResponse> {
  const headers = await procurementHeaders()

  const response = await fetch(
    `${API_BASE}/api/v1/procurement/purchase-requests/import`,
    {
      method: 'POST',
      headers,
      body: formData,
      cache: 'no-store',
    }
  )
  const result = await parseJsonResponse<PurchaseRequestImportResponse>(
    response,
    '采购申请导入失败'
  )
  if (response.ok) {
    revalidatePath('/purchasing')
  }
  return result
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

export async function submitPurchaseRequest(
  requestId: string
): Promise<PurchaseRequestApiResponse> {
  const response = await procurementJsonFetch<PurchaseRequestApiResponse>(
    `/api/v1/procurement/purchase-requests/${requestId}/submit`,
    {
      method: 'POST',
      body: JSON.stringify({}),
    },
    '采购申请提交失败'
  )
  revalidatePath('/purchasing')
  return response
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

export async function approvePurchaseRequest(
  requestId: string,
  payload: PurchaseApprovalRequest
): Promise<PurchaseRequestApiResponse> {
  const response = await procurementJsonFetch<PurchaseRequestApiResponse>(
    `/api/v1/procurement/purchase-requests/${requestId}/approve`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
    '审批失败'
  )
  revalidatePath('/purchasing')
  return response
}

export async function rejectPurchaseRequest(
  requestId: string,
  payload: PurchaseApprovalRequest
): Promise<PurchaseRequestApiResponse> {
  const response = await procurementJsonFetch<PurchaseRequestApiResponse>(
    `/api/v1/procurement/purchase-requests/${requestId}/reject`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
    '驳回失败'
  )
  revalidatePath('/purchasing')
  return response
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
