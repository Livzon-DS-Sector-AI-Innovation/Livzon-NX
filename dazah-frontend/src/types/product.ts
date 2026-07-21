export interface Product {
  id: string
  name: string
  major_category?: string
  formulation_code?: string
  product_type?: string
  spec?: string
  capacity_range?: string
  unit?: string
  indication?: string
  feishu_record_id?: string
  feishu_synced_at?: string
  created_at?: string
  updated_at?: string
}

export interface ProductCreateInput {
  name: string
  major_category?: string
  formulation_code?: string
  product_type?: string
  spec?: string
  capacity_range?: string
  unit?: string
  indication?: string
}

export interface ProductUpdateInput {
  name?: string
  major_category?: string
  formulation_code?: string
  product_type?: string
  spec?: string
  capacity_range?: string
  unit?: string
  indication?: string
}

export interface ProductListResponse {
  code: number
  message: string
  data: Product[]
  meta?: {
    page: number
    page_size: number
    total: number
  }
}

export interface ProductResponse {
  code: number
  message: string
  data: Product
}

export interface SyncStatusResponse {
  code: number
  message: string
  data: {
    local_total: number
    feishu_total: number
    synced_count: number
    unsynced_count: number
    last_sync_at: string | null
  }
}
