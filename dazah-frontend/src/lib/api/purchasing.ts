import type { operations } from '@/types/generated/schema'
import { getBackendFallbackUrls } from '@/lib/server-api'
import type {
  InvoiceRecognitionRecordListResponse,
  ContractRecordApiResponse,
  ContractRecordListResponse,
  MaterialOptionListResponse,
  MaterialSourceConfigApiResponse,
  PurchaseOrderListResponse,
  PurchaseRequestApiResponse,
  PurchaseRequestListResponse,
  SupplierListResponse,
} from '@/types/purchasing'

type InvoiceRecognitionRecordQuery =
  operations['list_invoice_records_api_v1_procurement_invoices_recognition_records_get']['parameters']['query']
type PurchaseRequestQuery =
  operations['list_purchase_request_records_api_v1_procurement_purchase_requests_get']['parameters']['query']
type PurchaseOrderQuery =
  operations['list_purchase_order_records_api_v1_procurement_purchase_orders_get']['parameters']['query']
type SupplierQuery =
  operations['list_supplier_records_api_v1_procurement_suppliers_get']['parameters']['query']
type ContractRecordQuery =
  operations['list_contract_generation_records_api_v1_procurement_contracts_get']['parameters']['query']
type MaterialOptionQuery =
  operations['list_material_option_records_api_v1_procurement_material_options_get']['parameters']['query']

function getServerApiBaseUrls() {
  return getBackendFallbackUrls()
}

async function apiFetch<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })
  if (!response.ok) {
    throw new Error(`请求失败: ${response.status} ${response.statusText}`)
  }
  const data = await response.json()
  return data.data ?? data
}

export async function fetchModuleInfo(): Promise<{ code: string; name: string; description: string }> {
  return apiFetch(`/api/v1/procurement/`)
}

export async function fetchInvoiceRecognitionRecords(
  query: InvoiceRecognitionRecordQuery = {},
  requestHeaders?: HeadersInit,
): Promise<InvoiceRecognitionRecordListResponse> {
  const params = new URLSearchParams()
  Object.entries(query).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    params.set(key, String(value))
  })

  const path = `/api/v1/procurement/invoices/recognition-records${
    params.size ? `?${params.toString()}` : ''
  }`
  if (typeof window !== 'undefined') {
    const response = await fetch(path, {
      cache: 'no-store',
    })

    if (!response.ok) {
      throw new Error(`请求失败: ${response.status} ${response.statusText}`)
    }

    return response.json()
  }

  let lastError: unknown
  for (const baseUrl of getServerApiBaseUrls()) {
    let response: Response
    try {
      response = await fetch(`${baseUrl}${path}`, {
        cache: 'no-store',
        headers: requestHeaders,
      })
    } catch (error) {
      lastError = error
      continue
    }

    if (!response.ok) {
      throw new Error(`请求失败: ${response.status} ${response.statusText}`)
    }

    return response.json()
  }

  throw lastError
}

export async function fetchPurchaseRequests(
  query: PurchaseRequestQuery = {},
  requestHeaders?: HeadersInit,
): Promise<PurchaseRequestListResponse> {
  const path = `/api/v1/procurement/purchase-requests${buildQueryString(query)}`
  return fetchApiWithServerFallback<PurchaseRequestListResponse>(path, requestHeaders)
}

export async function fetchMaterialOptions(
  query: MaterialOptionQuery,
  requestHeaders?: HeadersInit,
): Promise<MaterialOptionListResponse> {
  const path = `/api/v1/procurement/material-options${buildQueryString(query)}`
  return fetchApiWithServerFallback<MaterialOptionListResponse>(path, requestHeaders)
}

export async function fetchMaterialSourceConfig(
  requestHeaders?: HeadersInit,
): Promise<MaterialSourceConfigApiResponse> {
  return fetchApiWithServerFallback<MaterialSourceConfigApiResponse>(
    '/api/v1/procurement/material-source-config',
    requestHeaders,
  )
}

export async function fetchPurchaseOrders(
  query: PurchaseOrderQuery,
  requestHeaders?: HeadersInit,
): Promise<PurchaseOrderListResponse> {
  const path = `/api/v1/procurement/purchase-orders${buildQueryString(query)}`
  return fetchApiWithServerFallback<PurchaseOrderListResponse>(path, requestHeaders)
}

export async function fetchSuppliers(
  query: SupplierQuery = {},
  requestHeaders?: HeadersInit,
): Promise<SupplierListResponse> {
  const path = `/api/v1/procurement/suppliers${buildQueryString(query)}`
  return fetchApiWithServerFallback<SupplierListResponse>(path, requestHeaders)
}

export async function fetchContractRecords(
  query: ContractRecordQuery = {},
  requestHeaders?: HeadersInit,
): Promise<ContractRecordListResponse> {
  const path = `/api/v1/procurement/contracts${buildQueryString(query)}`
  return fetchApiWithServerFallback<ContractRecordListResponse>(path, requestHeaders)
}

export async function fetchContractRecord(
  contractId: string
): Promise<ContractRecordApiResponse> {
  return fetchApiWithServerFallback<ContractRecordApiResponse>(
    `/api/v1/procurement/contracts/${contractId}`
  )
}

export async function fetchContractFile(
  contractId: string
): Promise<{ blob: Blob; filename: string }> {
  const response = await fetchWithServerFallback(
    `/api/v1/procurement/contracts/${contractId}/file`
  )
  const blob = await response.blob()
  const docxBlob = blob.type
    ? blob
    : new Blob([blob], {
        type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      })
  return {
    blob: docxBlob,
    filename: parseDownloadFilenameWithDefault(
      response.headers.get('content-disposition'),
      '采购合同.docx'
    ),
  }
}

export async function exportPurchaseOrdersExcel(
  query: Omit<PurchaseOrderQuery, 'page' | 'page_size'>
): Promise<{ blob: Blob; filename: string }> {
  const path = `/api/v1/procurement/purchase-orders/export${buildQueryString(query)}`
  const response = await fetchWithServerFallback(path)
  const blob = await response.blob()
  const excelBlob = blob.type
    ? blob
    : new Blob([blob], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })
  return {
    blob: excelBlob,
    filename: parseDownloadFilename(response.headers.get('content-disposition')),
  }
}

export async function fetchPurchaseRequest(
  requestId: string
): Promise<PurchaseRequestApiResponse> {
  return fetchApiWithServerFallback<PurchaseRequestApiResponse>(
    `/api/v1/procurement/purchase-requests/${requestId}`
  )
}

function buildQueryString(query: Record<string, unknown>) {
  const params = new URLSearchParams()
  Object.entries(query).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    params.set(key, String(value))
  })
  return params.size ? `?${params.toString()}` : ''
}

function parseDownloadFilename(contentDisposition: string | null) {
  return parseDownloadFilenameWithDefault(contentDisposition, '采购订单.xlsx')
}

function parseDownloadFilenameWithDefault(contentDisposition: string | null, fallback: string) {
  if (!contentDisposition) return fallback

  const utf8Match = contentDisposition.match(/filename\*=utf-8''([^;]+)/i)
  if (utf8Match?.[1]) {
    return decodeURIComponent(utf8Match[1])
  }

  const asciiMatch = contentDisposition.match(/filename="?([^";]+)"?/i)
  return asciiMatch?.[1] ?? fallback
}

async function fetchWithServerFallback(
  path: string,
  requestHeaders?: HeadersInit,
): Promise<Response> {
  if (typeof window !== 'undefined') {
    const response = await fetch(path, { cache: 'no-store' })
    if (!response.ok) {
      throw new Error(`请求失败: ${response.status} ${response.statusText}`)
    }
    return response
  }

  let lastError: unknown
  for (const baseUrl of getServerApiBaseUrls()) {
    let response: Response
    try {
      response = await fetch(`${baseUrl}${path}`, {
        cache: 'no-store',
        headers: requestHeaders,
      })
    } catch (error) {
      lastError = error
      continue
    }

    if (!response.ok) {
      throw new Error(`请求失败: ${response.status} ${response.statusText}`)
    }

    return response
  }

  throw lastError
}

async function fetchApiWithServerFallback<T>(
  path: string,
  requestHeaders?: HeadersInit,
): Promise<T> {
  const response = await fetchWithServerFallback(path, requestHeaders)
  return response.json()
}
