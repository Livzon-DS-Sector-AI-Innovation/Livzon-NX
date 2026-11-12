// 摇瓶种子制备记录类型
// 人员字段为飞书成员引用数组（同步解析 open_id → 姓名+头像；
// 手工录入仅有姓名）。历史文本数据兼容为 [{name}] 形态由后端归一。

export interface SeedCulturePerson {
  name: string
  open_id?: string | null
  avatar_url?: string | null
}

export interface SeedCultureRecord {
  id: string
  batch_no: string
  product_name: string
  prepare_date?: string | null
  glucose_batch?: string | null
  corn_starch_batch?: string | null
  corn_syrup_batch?: string | null
  ammonium_sulfate_batch?: string | null
  soybean_meal_batch?: string | null
  calcium_carbonate_batch?: string | null
  prepare_operator?: SeedCulturePerson[] | null
  sterilization_operator?: SeedCulturePerson[] | null
  ph_before_adjust?: number | null
  ph_after_adjust?: number | null
  ph_after_sterilization?: number | null
  reducing_sugar?: number | null
  total_sugar?: number | null
  amino_nitrogen?: number | null
  strain_tube_no?: string | null
  shaker_setup_operator?: SeedCulturePerson[] | null
  shaker_no?: string | null
  shaker_start_date?: string | null
  inoculation_operator?: SeedCulturePerson[] | null
  tool_no?: string | null
  merge_time?: string | null
  merge_count?: number | null
  merge_cycle?: string | null
  merge_ph?: number | null
  merge_bacteria_density?: number | null
  merge_total_sugar?: string | number | null
  merge_reducing_sugar?: string | number | null
  merge_amino_nitrogen?: string | number | null
  tank_setup_operator?: SeedCulturePerson[] | null
  cylinder_no?: string | null
  merge_operator?: SeedCulturePerson[] | null
  workshop_inoculation_operator?: SeedCulturePerson[] | null
  tank_remarks?: string | null
  tank_yield?: number | null
  remarks?: string | null
  created_at: string
  updated_at: string
}

export interface SeedCultureCreate {
  batch_no: string
  product_name?: string
  prepare_date?: string | null
  glucose_batch?: string | null
  corn_starch_batch?: string | null
  corn_syrup_batch?: string | null
  ammonium_sulfate_batch?: string | null
  soybean_meal_batch?: string | null
  calcium_carbonate_batch?: string | null
  prepare_operator?: SeedCulturePerson[] | null
  sterilization_operator?: SeedCulturePerson[] | null
  ph_before_adjust?: number | null
  ph_after_adjust?: number | null
  ph_after_sterilization?: number | null
  reducing_sugar?: number | null
  total_sugar?: number | null
  amino_nitrogen?: number | null
  strain_tube_no?: string | null
  shaker_setup_operator?: SeedCulturePerson[] | null
  shaker_no?: string | null
  shaker_start_date?: string | null
  inoculation_operator?: SeedCulturePerson[] | null
  tool_no?: string | null
  merge_time?: string | null
  merge_count?: number | null
  merge_cycle?: string | null
  merge_ph?: number | null
  merge_bacteria_density?: number | null
  merge_total_sugar?: string | number | null
  merge_reducing_sugar?: string | number | null
  merge_amino_nitrogen?: string | number | null
  tank_setup_operator?: SeedCulturePerson[] | null
  cylinder_no?: string | null
  merge_operator?: SeedCulturePerson[] | null
  workshop_inoculation_operator?: SeedCulturePerson[] | null
  tank_remarks?: string | null
  tank_yield?: number | null
  remarks?: string | null
}

export type SeedCultureUpdate = Partial<SeedCultureCreate>


// 人员月度工作统计（绩效依据）：月 × 人聚合
export interface PersonMonthlyDetail {
  date: string
  batch_no: string
  role: string
}

export interface PersonMonthlyRow {
  key: string
  name: string
  open_id?: string | null
  avatar_url?: string | null
  total_batches: number
  role_counts: Record<string, number>
  details: PersonMonthlyDetail[]
}
