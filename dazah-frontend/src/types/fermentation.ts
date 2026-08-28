// Fermentation record types

export interface FermentationRecord {
  id: string
  batch_no: string
  product_name: string
  fermenter: string
  entry_date: string
  discharge_date?: string | null
  cycle_1?: number | null
  cycle_2?: number | null
  cycle_3?: number | null
  cycle_4?: number | null
  cycle_5?: number | null
  cycle_6?: number | null
  tank_yield?: number | null
  status: string
  remarks?: string | null
  attachment?: string | null
  created_at: string
  updated_at: string
}

export interface FermentationCreate {
  batch_no: string
  product_name: string
  fermenter: string
  entry_date: string
  discharge_date?: string | null
  cycle_1?: number | null
  cycle_2?: number | null
  cycle_3?: number | null
  cycle_4?: number | null
  cycle_5?: number | null
  cycle_6?: number | null
  tank_yield?: number | null
  status?: string
  remarks?: string | null
  attachment?: string | null
}

export interface FermentationUpdate {
  batch_no?: string
  fermenter?: string
  entry_date?: string
  discharge_date?: string | null
  cycle_1?: number | null
  cycle_2?: number | null
  cycle_3?: number | null
  cycle_4?: number | null
  cycle_5?: number | null
  cycle_6?: number | null
  tank_yield?: number | null
  status?: string
  remarks?: string | null
  attachment?: string | null
}

export const FERMENTATION_STATUS_OPTIONS = [
  { value: 'in_progress', label: '运行中', color: 'processing' },
  { value: 'completed', label: '已完成', color: 'success' },
  { value: 'abnormal', label: '异常', color: 'error' },
]
