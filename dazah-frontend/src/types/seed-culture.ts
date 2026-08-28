// 摇瓶种子制备记录类型

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
  prepare_operator?: string | null
  sterilization_operator?: string | null
  ph_before_adjust?: number | null
  ph_after_adjust?: number | null
  ph_after_sterilization?: number | null
  reducing_sugar?: number | null
  total_sugar?: number | null
  amino_nitrogen?: number | null
  strain_tube_no?: string | null
  shaker_setup_operator?: string | null
  shaker_no?: string | null
  shaker_start_date?: string | null
  inoculation_operator?: string | null
  tool_no?: string | null
  merge_time?: string | null
  merge_count?: number | null
  merge_cycle?: string | null
  merge_ph?: number | null
  merge_bacteria_density?: number | null
  merge_total_sugar?: number | null
  merge_reducing_sugar?: number | null
  merge_amino_nitrogen?: number | null
  tank_setup_operator?: string | null
  cylinder_no?: string | null
  merge_operator?: string | null
  workshop_inoculation_operator?: string | null
  tank_remarks?: string | null
  tank_yield?: number | null
  remarks?: string | null
  created_at: string
  updated_at: string
}

export interface SeedCultureCreate {
  batch_no: string
  product_name: string
  prepare_date?: string | null
  glucose_batch?: string | null
  corn_starch_batch?: string | null
  corn_syrup_batch?: string | null
  ammonium_sulfate_batch?: string | null
  soybean_meal_batch?: string | null
  calcium_carbonate_batch?: string | null
  prepare_operator?: string | null
  sterilization_operator?: string | null
  ph_before_adjust?: number | null
  ph_after_adjust?: number | null
  ph_after_sterilization?: number | null
  reducing_sugar?: number | null
  total_sugar?: number | null
  amino_nitrogen?: number | null
  strain_tube_no?: string | null
  shaker_setup_operator?: string | null
  shaker_no?: string | null
  shaker_start_date?: string | null
  inoculation_operator?: string | null
  tool_no?: string | null
  merge_time?: string | null
  merge_count?: number | null
  merge_cycle?: string | null
  merge_ph?: number | null
  merge_bacteria_density?: number | null
  merge_total_sugar?: number | null
  merge_reducing_sugar?: number | null
  merge_amino_nitrogen?: number | null
  tank_setup_operator?: string | null
  cylinder_no?: string | null
  merge_operator?: string | null
  workshop_inoculation_operator?: string | null
  tank_remarks?: string | null
  tank_yield?: number | null
  remarks?: string | null
}

export type SeedCultureUpdate = Partial<SeedCultureCreate>
