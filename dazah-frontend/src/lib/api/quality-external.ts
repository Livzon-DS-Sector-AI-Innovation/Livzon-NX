import type { components } from '@/types/generated/schema'

export type Supplier = components['schemas']['SupplierOut']
export type SupplierQualification = components['schemas']['SupplierQualificationOut']
export type Complaint = components['schemas']['ComplaintOut']
export type ReturnRecall = components['schemas']['ReturnRecallOut']
export type ProductQualityRecord = components['schemas']['ProductQualityRecordOut']
export type ProductQualityStandardItem = components['schemas']['ProductQualityStandardItemOut']

type ListEnvelope<T> = { code?: number; message?: string; data: T[]; meta?: { total?: number; page?: number; page_size?: number } }
export type SupplierListResponse = ListEnvelope<Supplier>
export type SupplierQualificationListResponse =
  components['schemas']['SupplierQualificationListResponse']
export type ComplaintListResponse = ListEnvelope<Complaint>
export type ReturnRecallListResponse = ListEnvelope<ReturnRecall>
export type ProductQualityRecordListResponse = ListEnvelope<ProductQualityRecord>
export type ProductQualityStandardItemListResponse =
  components['schemas']['ProductQualityStandardItemListResponse']

async function externalQualityGet<T>(path: string): Promise<T> {
  const response = await fetch(path, { cache: 'no-store' })
  if (!response.ok) {
    throw new Error(`读取外部质量数据失败：${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<T>
}

function listPath(path: string, params?: Record<string, string | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value) search.set(key, value)
  }
  search.set('page', '1')
  search.set('page_size', '50')
  return `${path}?${search.toString()}`
}

export async function fetchSuppliers(): Promise<SupplierListResponse> {
  return externalQualityGet<SupplierListResponse>(listPath('/api/v1/quality/suppliers'))
}

export async function fetchSupplierQualifications(
  supplierId: string,
): Promise<SupplierQualificationListResponse> {
  return externalQualityGet<SupplierQualificationListResponse>(
    `/api/v1/quality/suppliers/${supplierId}/qualifications`,
  )
}

export async function fetchComplaints(): Promise<ComplaintListResponse> {
  return externalQualityGet<ComplaintListResponse>(listPath('/api/v1/quality/complaints'))
}

export async function fetchReturnRecalls(): Promise<ReturnRecallListResponse> {
  return externalQualityGet<ReturnRecallListResponse>(
    listPath('/api/v1/quality/return-recalls'),
  )
}

export async function fetchProductQualityRecords(): Promise<ProductQualityRecordListResponse> {
  return externalQualityGet<ProductQualityRecordListResponse>(
    listPath('/api/v1/quality/product-quality'),
  )
}

export async function fetchProductQualityStandardItems(
  recordId: string,
): Promise<ProductQualityStandardItemListResponse> {
  return externalQualityGet<ProductQualityStandardItemListResponse>(
    `/api/v1/quality/product-quality/${recordId}/standard-items`,
  )
}
